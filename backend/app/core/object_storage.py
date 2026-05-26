"""
Object Storage (Naver Cloud S3 호환)

경로 구조:
  uploads/tmp/{uuid}.{ext}            - 임시 (24시간 후 자동 삭제)
  uploads/perm/{prefix}/{uuid}.{ext}  - 영구 (prefix는 호출 측에서 결정)

사용법:
  from app.core.object_storage import get_object_storage 

  object_storage = get_object_storage()

  # 임시 업로드
  url = await object_storage.upload_temp(file, "photo.jpg", "image/jpeg")

  # 영구 저장소로 이동 (prefix는 호출 측에서 생성)
  perm_url = await object_storage.move_to_perm(temp_url=url, prefix="user123/posts/post456")

  # 직접 영구 업로드
  url = await object_storage.upload_perm(file, "photo.jpg", "image/jpeg", prefix="user123/posts/post456")

  # 삭제
  await object_storage.delete(url)
"""
import uuid
from typing import BinaryIO, List
from botocore.exceptions import ClientError
from botocore.config import Config
import boto3
import asyncio

from app.core.logger import get_logger
from app.config.setting import settings


logger = get_logger("object_storage")

_PREFIX_TMP = "uploads/tmp"
_PREFIX_PERM = "uploads/perm"


class ObjectStorage:
    """Naver Cloud S3 호환 Object Storage 클라이언트"""

    _instance: "ObjectStorage | None" = None

    def __init__(self):
        self.bucket = settings.S3_BUCKET_NAME
        self.endpoint = settings.S3_ENDPOINT_URL

        self._client = boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=settings.S3_ACCESS_KEY_ID,
            aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
            config=Config(
                region_name=settings.S3_REGION,
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )


    @classmethod
    def get_instance(cls) -> "ObjectStorage":
        """싱글톤 인스턴스 반환 (최초 호출 시 초기화)"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ──────────────────── 업로드 ────────────────────

    async def upload_temp(self, file: BinaryIO, file_name: str, content_type: str) -> str:
        """임시 경로에 업로드 → URL 반환"""
        key = self._make_key(file_name, _PREFIX_TMP)
        return await asyncio.to_thread(self._upload, file, key, content_type)


    async def upload_perm(self, file: BinaryIO, file_name: str, content_type: str, *, prefix: str) -> str:
        """영구 경로에 직접 업로드 → URL 반환"""
        key = self._make_key(file_name, f"{_PREFIX_PERM}/{prefix}")
        return await asyncio.to_thread(self._upload, file, key, content_type)


    async def upload_to_key(
        self,
        file: "BinaryIO | bytes",
        *,
        prefix: str,
        filename: str,
        content_type: str,
    ) -> str:
        """결정적 키 (`{_PREFIX_PERM}/{prefix}/{filename}`) 로 업로드 → URL 반환.

        `upload_perm` 과 달리 자동 UUID 생성 없이 호출자가 지정한 filename 을 그대로 사용한다.
        피드 다해상도 변형 (`small.jpg` / `medium.jpg` / `original.{ext}`) 처럼 같은 디렉터리
        하위에 결정적 이름으로 묶어야 하는 케이스 전용.
        """
        key = f"{_PREFIX_PERM}/{prefix}/{filename}"
        if isinstance(file, (bytes, bytearray)):
            import io
            file = io.BytesIO(file)
        return await asyncio.to_thread(self._upload, file, key, content_type)

    # ──────────────────── 이동 (tmp → perm) ────────────────────

    async def move_to_perm(self, temp_url: str, *, prefix: str) -> str:
        """임시 파일 1개를 영구 경로로 이동 → 새 URL 반환"""
        src_key = self._url_to_key(temp_url)
        filename = src_key.rsplit("/", 1)[-1]
        dst_key = f"{_PREFIX_PERM}/{prefix}/{filename}"

        await asyncio.to_thread(self._copy, src_key, dst_key)
        await asyncio.to_thread(self._delete, src_key)

        logger.info("파일 이동 완료: {} → {}", src_key, dst_key)
        return self._key_to_url(dst_key)


    async def move_many_to_perm(self, temp_urls: List[str], *, prefix: str) -> List[str]:
        """임시 파일 여러 개를 영구 경로로 이동 → 새 URL 목록 반환"""
        return list(await asyncio.gather(
            *(self.move_to_perm(url, prefix=prefix) for url in temp_urls)
        ))

    # ──────────────────── 삭제 ────────────────────

    async def delete(self, file_url: str) -> None:
        """URL로 파일 삭제"""
        key = self._url_to_key(file_url)
        await asyncio.to_thread(self._delete, key)
        logger.info("파일 삭제 완료: {}", key)


    async def delete_many(self, file_urls: List[str]) -> None:
        """URL 목록으로 파일 일괄 삭제"""
        if not file_urls:
            return

        objects = [{"Key": self._url_to_key(url)} for url in file_urls]
        try:
            await asyncio.to_thread(
                self._client.delete_objects, Bucket=self.bucket, Delete={"Objects": objects},
            )
            logger.info("파일 일괄 삭제 완료: {:d}건", len(objects))
        except ClientError as e:
            logger.error("파일 일괄 삭제 실패: {}", e)
            raise


    async def delete_by_prefix(self, prefix: str) -> int:
        """특정 경로(prefix) 하위 파일 전체 삭제 → 삭제 건수 반환"""
        full_prefix = f"{_PREFIX_PERM}/{prefix}"
        deleted = await asyncio.to_thread(self._delete_by_prefix_sync, full_prefix)
        logger.info("prefix 삭제 완료: {} ({:d}건)", full_prefix, deleted)
        return deleted

    # ──────────────────── 조회 ────────────────────

    def get_url(self, file_key: str) -> str:
        """파일 키 → URL"""
        return self._key_to_url(file_key)

    # ──────────────────── 내부 헬퍼 ────────────────────

    def _make_key(self, file_name: str, prefix: str) -> str:
        ext = file_name.rsplit(".", 1)[-1] if "." in file_name else ""
        unique = uuid.uuid4()
        return f"{prefix}/{unique}.{ext}" if ext else f"{prefix}/{unique}"


    def _key_to_url(self, key: str) -> str:
        return f"{self.endpoint}/{self.bucket}/{key}"


    def _url_to_key(self, url: str) -> str:
        base = f"{self.endpoint}/{self.bucket}/"
        if not url.startswith(base):
            raise ValueError(f"올바르지 않은 Object Storage URL: {url}")
        return url[len(base):]


    def _upload(self, file: BinaryIO, key: str, content_type: str) -> str:
        try:
            self._client.upload_fileobj(
                file, self.bucket, key,
                ExtraArgs={"ContentType": content_type, "ACL": "public-read"},
            )
        except ClientError as e:
            logger.error("업로드 실패 ({}): {}", key, e)
            raise
        logger.info("업로드 완료: {}", key)
        return self._key_to_url(key)


    def _copy(self, src_key: str, dst_key: str) -> None:
        try:
            self._client.copy_object(
                Bucket=self.bucket,
                CopySource={"Bucket": self.bucket, "Key": src_key},
                Key=dst_key,
                ACL="public-read",
            )
        except ClientError as e:
            logger.error("복사 실패 ({} → {}): {}", src_key, dst_key, e)
            raise


    def _delete_by_prefix_sync(self, full_prefix: str) -> int:
        paginator = self._client.get_paginator("list_objects_v2")
        deleted = 0
        for page in paginator.paginate(Bucket=self.bucket, Prefix=full_prefix):
            objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
            if not objects:
                continue
            self._client.delete_objects(Bucket=self.bucket, Delete={"Objects": objects})
            deleted += len(objects)
        return deleted


    def _delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self.bucket, Key=key)
        except ClientError as e:
            logger.error("삭제 실패 ({}): {}", key, e)
            raise


def get_object_storage() -> ObjectStorage:
    """ObjectStorage 싱글톤 인스턴스 반환"""
    return ObjectStorage.get_instance()
