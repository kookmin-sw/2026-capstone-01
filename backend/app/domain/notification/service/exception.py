"""인박스 도메인 예외. Router 가 404 로 매핑."""


class InboxItemNotFoundError(Exception):
    """미존재 / 타인 소유 / 이미 hide / 잘못된 id 형식 — 정보 누출 회피로 일원화."""
