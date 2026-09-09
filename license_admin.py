#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Admin helper for issuing signed one-machine-one-code licenses."""

import argparse
import json
import sys
import uuid
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import rsa

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.license import normalize_hwid_to_machine_code, sign_license_record


def generate_keypair(
    private_key_path: str,
    public_key_path: str,
    key_size: int = 2048,
) -> None:
    public_key, private_key = rsa.newkeys(key_size)
    Path(private_key_path).write_bytes(private_key.save_pkcs1())
    Path(public_key_path).write_bytes(public_key.save_pkcs1())


def load_private_key(private_key_path: str) -> str:
    return Path(private_key_path).read_text(encoding="utf-8")


def create_license_record(
    hwid: str,
    private_key_pem: str,
    expires_at: str,
    features: Optional[Iterable[str]] = None,
    license_id: Optional[str] = None,
    issued_at: Optional[str] = None,
    owner: Optional[str] = None,
    note: Optional[str] = None,
) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "license_id": license_id or str(uuid.uuid4()),
        "hwid_hash": normalize_hwid_to_machine_code(hwid),
        "expires_at": expires_at,
        "features": list(features or ["full"]),
        "issued_at": issued_at or date.today().isoformat(),
    }
    if owner:
        record["owner"] = owner
    if note:
        record["note"] = note

    record["signature"] = sign_license_record(record, private_key_pem)
    return record


def load_license_collection(path: str) -> Dict[str, Any]:
    license_path = Path(path)
    if not license_path.exists():
        return {"version": 1, "licenses": []}
    with open(license_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return {"version": 1, "licenses": data}
    if isinstance(data, dict):
        data.setdefault("version", 1)
        data.setdefault("licenses", [])
        return data
    return {"version": 1, "licenses": []}


def save_license_collection(path: str, collection: Dict[str, Any]) -> None:
    collection["updated_at"] = date.today().isoformat()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(collection, f, ensure_ascii=False, indent=2)
        f.write("\n")


def append_license_record(path: str, record: Dict[str, Any]) -> Dict[str, Any]:
    collection = load_license_collection(path)
    licenses: List[Dict[str, Any]] = collection.setdefault("licenses", [])
    licenses[:] = [
        item for item in licenses
        if item.get("hwid_hash") != record.get("hwid_hash")
    ]
    licenses.append(record)
    save_license_collection(path, collection)
    return collection


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成一机一码授权文件")
    subparsers = parser.add_subparsers(dest="command", required=True)

    key_parser = subparsers.add_parser("gen-key", help="生成 RSA 公私钥")
    key_parser.add_argument("--private-key", default="license_private.pem")
    key_parser.add_argument("--public-key", default="license_public.pem")
    key_parser.add_argument("--key-size", type=int, default=2048)

    issue_parser = subparsers.add_parser("issue", help="为一个机器码签发授权")
    issue_parser.add_argument("--hwid", required=True, help="客户发来的机器码")
    issue_parser.add_argument("--private-key", default="license_private.pem")
    issue_parser.add_argument("--expires-at", default="permanent")
    issue_parser.add_argument("--features", default="full")
    issue_parser.add_argument("--license-id")
    issue_parser.add_argument("--owner")
    issue_parser.add_argument("--note")
    issue_parser.add_argument("--licenses", help="licenses.json 路径；提供后会自动写入")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "gen-key":
        generate_keypair(args.private_key, args.public_key, args.key_size)
        print(f"私钥: {args.private_key}")
        print(f"公钥: {args.public_key}")
        print("请妥善保管私钥，不要放进 exe，也不要上传到 Gitee。")
        return 0

    if args.command == "issue":
        private_key_pem = load_private_key(args.private_key)
        features = [item.strip() for item in args.features.split(",") if item.strip()]
        record = create_license_record(
            hwid=args.hwid,
            private_key_pem=private_key_pem,
            expires_at=args.expires_at,
            features=features,
            license_id=args.license_id,
            owner=args.owner,
            note=args.note,
        )
        if args.licenses:
            append_license_record(args.licenses, record)
            print(f"已写入: {args.licenses}")
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
