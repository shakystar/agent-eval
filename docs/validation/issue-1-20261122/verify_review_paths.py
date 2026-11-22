"""저장된 네이티브 영수증과 대조해 9개 슬롯의 역할 순서와 검토 분기를 검사한다."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re


def require(value, message):
    if not value:
        raise ValueError(message)


def read_blob(blobs, digest):
    require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest), "잘못된 SHA-256")
    data = (blobs / digest).read_bytes()
    require(sha256(data).hexdigest() == digest, "저장 증거 해시 불일치")
    return data


def verify_slot(label, slot, blobs, backend):
    require(slot["status"] == "completed", "미완료 슬롯")
    rows = slot["stages"]
    names = [row["stage"] for row in rows]
    solo = label.startswith("solo-")
    require(names == ["write"] if solo else names[:2] == ["write", "review"],
            "작성 또는 첫 검토 단계 누락·순서 오류")

    decisions = {}
    document = None
    for row in rows:
        name = row["stage"]
        require(name in ("write", "review", "revise", "final-review"), "알 수 없는 단계")
        require(row["status"] == "completed", f"{name} 미완료")
        native = json.loads(read_blob(blobs, row["receipt_sha256"]))
        wire = json.loads(read_blob(blobs, row["wire_sha256"]))
        output = read_blob(blobs, row["output_sha256"]).decode("utf-8")
        role = "writer" if name in ("write", "revise") else "reviewer"
        require(native["status"] == "succeeded" and native["task"]["id"] == wire["id"] == name
                and native["task"]["role"] == wire["role"] == role, f"{name} 단계·역할·영수증 불일치")
        require(wire["attempt_id"] == row["attempt_id"] and native["result"]["text"] == output,
                f"{name} 시도 또는 출력 불일치")
        if role == "writer":
            document = row["output_sha256"]
            continue
        review = json.loads(output)
        require(review["verdict"] in ("accept", "revise", "defer")
                and isinstance(review["reason"], str) and review["reason"].strip(), "유효한 검토 판정 없음")
        decisions[name] = review["verdict"]

    require(slot["decisions"] == decisions and slot["document"] == document,
            "공개 판정 또는 최종 산출물이 영수증과 불일치")
    if not solo:
        expected = ["write", "review"]
        if decisions["review"] == "revise":
            expected.extend(["revise", "final-review"])
        require(names == expected, "첫 검토 판정과 후속 단계 불일치")
        if backend == "fixture" or label == "revision-1":
            require(decisions == {"review": "revise", "final-review": "accept"}, "예정된 수정·최종 수락 미확인")
    return len(rows)


def verify(results, store, backend):
    require(results["backend"] == backend, "백엔드 불일치")
    expected = {f"{condition}-{repeat}" for condition in ("solo", "team", "material", "fault") for repeat in (1, 2)}
    expected.add("revision-1")
    slots = results["slots"]
    require(slots.keys() == expected, "예정된 슬롯과 결과 집합 불일치")
    steps = 0
    for label, slot in slots.items():
        try:
            steps += verify_slot(label, slot, store / "blobs", backend)
        except (KeyError, OSError, TypeError, ValueError) as exc:
            raise ValueError(f"{label}: {exc}") from exc
    return {"backend": backend, "slots": len(slots), "stages": steps}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backend", choices=("fixture", "codex"))
    parser.add_argument("results", type=Path)
    parser.add_argument("store", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(json.loads(args.results.read_bytes()), args.store, args.backend)))
