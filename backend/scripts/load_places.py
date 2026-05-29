"""서울 관광 장소 데이터 MongoDB 벌크 업로드 스크립트

사용법:
    # .env 기본 설정 사용 (Docker 환경)
    python scripts/load_places.py

    # MongoDB URL 직접 지정 (로컬 테스트)
    python scripts/load_places.py --mongodb-url mongodb://cho:hyeonsang@localhost:27017/chohyeonsang?authSource=admin

    # 데이터 디렉토리 지정
    python scripts/load_places.py --data-dir ./seoul_data

동작:
    1. 기존 place 컬렉션 삭제 (초기화)
    2. seoul_data/*.json 파일을 순서대로 읽음
    3. location을 GeoJSON Point 형식으로 변환
    4. insert_many로 벌크 삽입
    5. 인덱스 생성 (2dsphere, rating)
"""

import sys
import re
from pathlib import Path
import json
import asyncio
import argparse

from pymongo import GEOSPHERE
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie


# ── 프로젝트 루트를 sys.path에 추가 (app 모듈 import를 위해) ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.domain.tour.model.place import Place


# ──────────────────── 이미지 URL 매핑 ────────────────────


def load_image_map(image_file: Path) -> dict[str, str]:
    """image_url.txt → {place_id: url} 매핑

    파일 포맷: 한 줄당 하나의 URL (`.../places/{place_id}.jpg`).
    파일이 없으면 빈 dict 반환 → 모든 장소가 photos=[] 로 저장됨.
    """
    image_map: dict[str, str] = {}
    if not image_file.exists():
        return image_map

    with open(image_file, "r", encoding="utf-8") as f:
        for line in f:
            url = line.strip()
            if not url:
                continue
            place_id = url.rsplit("/", 1)[-1].removesuffix(".jpg")
            image_map[place_id] = url
    return image_map


# ──────────────────── 데이터 변환 ────────────────────


def transform_place(raw: dict, image_map: dict[str, str]) -> dict:
    """원본 JSON → Place Document 형식으로 변환"""

    # location: {lat, lng} → GeoJSON {type, coordinates: [lng, lat]}
    loc = raw.get("location") or {}
    raw["location"] = {
        "type": "Point",
        "coordinates": [loc.get("lng", 0.0), loc.get("lat", 0.0)],
    }

    # rating_stars 제거 (Place 모델에 없는 필드)
    raw.pop("rating_stars", None)

    # reviews: null → [] 변환 + 내부 rating_stars 제거
    reviews = raw.get("reviews") or []
    for review in reviews:
        review.pop("rating_stars", None)
    raw["reviews"] = reviews

    # photos: image_map에 place_id가 있으면 URL 부착, 없으면 빈 배열
    image_url = image_map.get(raw.get("place_id"))
    raw["photos"] = [image_url] if image_url else []

    return raw


# ──────────────────── 파일 정렬 ────────────────────


def sort_key(path: Path) -> int:
    """final_data123.json → 123 (숫자 기준 정렬)"""
    match = re.search(r"(\d+)", path.stem)
    return int(match.group(1)) if match else 0


# ──────────────────── 메인 로직 ────────────────────


async def load_places(mongodb_url: str, data_dir: Path):
    # MongoDB 연결
    client = AsyncIOMotorClient(mongodb_url, tz_aware=True)
    db_name = mongodb_url.rsplit("/", 1)[-1].split("?")[0]
    database = client[db_name]

    # Beanie 초기화
    await init_beanie(database=database, document_models=[Place])

    # 기존 컬렉션 삭제 후 새로 시작
    collection = Place.get_motor_collection()
    await collection.drop()
    print("[초기화] place 컬렉션 삭제 완료")

    # 인덱스 생성 (drop으로 Beanie가 만든 인덱스도 삭제되므로 전부 재생성)
    await collection.create_index("place_id", unique=True)     # 장소 고유 식별자
    await collection.create_index("category")                  # 카테고리 필터링용
    await collection.create_index([("location", GEOSPHERE)])   # 근처 장소 검색용
    await collection.create_index([("rating", -1)])            # 별점 정렬용 (단일 필드 인덱스는 양방향 탐색 가능)
    await collection.create_index("types")                     # 장소 타입 필터링용
    print(f"[연결 완료] {db_name}")

    # JSON 파일 수집 및 정렬
    files = sorted(data_dir.glob("final_data*.json"), key=sort_key)
    if not files:
        print(f"[오류] {data_dir}에 final_data*.json 파일이 없습니다.")
        return

    # 이미지 URL 매핑 로드 (place_id → URL) — 한 번만 읽어 메모리 보관 후 변환에 재사용
    image_map = load_image_map(data_dir / "image_url.txt")
    print(f"[이미지 매핑] {len(image_map)}개 로드 완료")

    print(f"[시작] {len(files)}개 파일, 데이터 디렉토리: {data_dir}")

    total_inserted = 0
    matched_images = 0

    for i, file_path in enumerate(files, 1):
        with open(file_path, "r", encoding="utf-8") as f:
            raw_places = json.load(f)

        # 변환
        docs = [transform_place(raw, image_map) for raw in raw_places]
        matched_images += sum(1 for d in docs if d["photos"])

        # insert_many 실행 (drop 후 신규 삽입이므로 upsert 불필요)
        result = await collection.insert_many(docs)
        total_inserted += len(result.inserted_ids)

        # 진행률 (10파일마다 또는 마지막 파일)
        if i % 10 == 0 or i == len(files):
            print(f"  [{i}/{len(files)}] 삽입: {total_inserted}")

    print(f"\n[완료] 총 삽입: {total_inserted}, 이미지 부착: {matched_images}")

    # 인덱스 확인
    indexes = await collection.index_information()
    print(f"[인덱스] {list(indexes.keys())}")

    client.close()


# ──────────────────── CLI ────────────────────


def main():
    parser = argparse.ArgumentParser(description="서울 장소 데이터 MongoDB 벌크 업로드")
    parser.add_argument(
        "--mongodb-url",
        default=None,
        help="MongoDB 접속 URL (미지정 시 .env 설정 사용)",
    )
    parser.add_argument(
        "--data-dir",
        default=str(PROJECT_ROOT / "seoul_data"),
        help="JSON 데이터 디렉토리 경로 (기본: ./seoul_data)",
    )
    args = parser.parse_args()

    # MongoDB URL 결정
    if args.mongodb_url:
        mongodb_url = args.mongodb_url
    else:
        from app.config.setting import settings
        mongodb_url = settings.MONGODB_URL

    asyncio.run(load_places(mongodb_url, Path(args.data_dir)))


if __name__ == "__main__":
    main()
