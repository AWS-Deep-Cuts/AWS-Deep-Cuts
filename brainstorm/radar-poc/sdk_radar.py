#!/usr/bin/env python3
"""Deep Cuts Radar (PoC): botocore の Git 履歴から AWS サービスの「誕生・沈黙・廃盤」を読む。

使い方:
  git clone --filter=blob:none --no-checkout https://github.com/boto/botocore.git
  python3 sdk_radar.py ./botocore --since 2025-07-01 > radar.md

- サービス = botocore/data/<service>/ ディレクトリ、API モデル = service-2.json(.gz)
- 追加日 / 削除日 = そのサービスの API モデルが最初に追加 / 最後に削除されたコミット日
- 活動量 = 直近 12 か月で API モデルを変更したコミット数（40 サービス超を一括変更したコミットは除外）
注意: SDK への追加・削除日はサービスの発表日・終了日と一致しない。あくまで「兆候」として扱うこと。
"""
import argparse
import collections
import datetime
import gzip
import json
import re
import subprocess

MODEL_GLOBS = ["botocore/data/*/*/service-2.json", "botocore/data/*/*/service-2.json.gz"]
BULK_COMMIT_THRESHOLD = 40


def git(repo, *args):
    return subprocess.check_output(["git", "-C", repo, *args])


def git_text(repo, *args):
    return git(repo, *args).decode()


def parse_log(text):
    """`git log --format=@<date> --name-status` の出力を (日付, ステータス, サービス) に分解する。"""
    date = None
    for line in text.splitlines():
        if line.startswith("@"):
            date = line[1:]
        elif "\t" in line:
            status, path = line.split("\t", 1)
            yield date, status, path.split("/")[2]


def current_services(repo):
    entries = git_text(repo, "ls-tree", "HEAD", "botocore/data/").splitlines()
    return {e.split("\t")[1].split("/")[-1] for e in entries if " tree " in e}


def load_model(repo, service):
    versions = sorted(v for v in git_text(repo, "ls-tree", "--name-only", f"HEAD:botocore/data/{service}/").split()
                      if re.match(r"\d{4}-\d{2}-\d{2}$", v))
    version = versions[-1]
    files = git_text(repo, "ls-tree", "--name-only", f"HEAD:botocore/data/{service}/{version}/").split()
    name = next(f for f in files if f.startswith("service-2.json"))
    raw = git(repo, "show", f"HEAD:botocore/data/{service}/{version}/{name}")
    return json.loads(gzip.decompress(raw) if name.endswith(".gz") else raw)


def first_sentence(html):
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()
    return text.split(". ")[0][:200]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", help="botocore のクローン（--filter=blob:none で可）")
    parser.add_argument("--since", default="2025-07-01", help="新サービスとして列挙する起点日")
    parser.add_argument("--top", type=int, default=30)
    args = parser.parse_args()

    log = git_text(args.repo, "log", "--format=@%ad", "--date=short", "--name-status",
                   "--diff-filter=AD", "--", *MODEL_GLOBS)
    added, removed_on = {}, {}
    for date, status, service in parse_log(log):
        if status == "A":
            added[service] = min(added.get(service, date), date)
        elif status == "D":
            removed_on[service] = max(removed_on.get(service, date), date)

    alive = current_services(args.repo)
    removed = sorted(((d, s) for s, d in removed_on.items() if s not in alive), reverse=True)

    print(f"# Deep Cuts Radar（botocore HEAD: {git_text(args.repo, 'log', '-1', '--format=%h %ad', '--date=short').strip()}）\n")
    print(f"- 履歴上のサービス数: {len(added)} / 現存: {len(alive & set(added))} / SDK から削除: {len(removed)}\n")

    print("## 年別のサービス追加数・削除数\n\n| 年 | 追加 | 削除 |\n|---|---|---|")
    add_by_year = collections.Counter(d[:4] for d in added.values())
    del_by_year = collections.Counter(d[:4] for d, _ in removed)
    for year in sorted(set(add_by_year) | set(del_by_year)):
        print(f"| {year} | {add_by_year[year]} | {del_by_year[year]} |")

    print("\n## SDK から削除されたサービス（廃盤候補）\n\n| 削除日 | サービス | SDK 追加日 |\n|---|---|---|")
    for date, service in removed:
        print(f"| {date} | `{service}` | {added.get(service, '?')} |")

    print(f"\n## {args.since} 以降に追加されたサービス（新譜）\n\n| SDK 追加日 | サービス | 正式名称 | 概要（ドキュメント冒頭） |\n|---|---|---|---|")
    for service, date in sorted(added.items(), key=lambda kv: kv[1], reverse=True):
        if date >= args.since and service in alive:
            model = load_model(args.repo, service)
            full_name = model.get("metadata", {}).get("serviceFullName", "")
            summary = first_sentence(model.get("documentation")).replace("|", "/")
            print(f"| {date} | `{service}` | {full_name} | {summary} |")

    one_year_ago = (datetime.date.today() - datetime.timedelta(days=365)).isoformat()
    three_years_ago = (datetime.date.today() - datetime.timedelta(days=3 * 365)).isoformat()
    log = git_text(args.repo, "log", f"--since={three_years_ago}", "--format=@%ad", "--date=short",
                   "--name-only", "--", *MODEL_GLOBS)
    commits = []  # [(日付, そのコミットで API モデルが変わったサービスの集合)]
    for line in log.splitlines():
        if line.startswith("@"):
            commits.append((line[1:], set()))
        elif line:
            commits[-1][1].add(line.split("/")[2])
    last_change, activity = {}, collections.Counter()
    for date, services in commits:
        if len(services) > BULK_COMMIT_THRESHOLD:
            continue
        for service in services:
            last_change[service] = max(last_change.get(service, date), date)
            if date >= one_year_ago:
                activity[service] += 1

    print(f"\n## 沈黙しているサービス（{three_years_ago} 以降の最終 API モデル変更が古い順）\n\n| 最終変更 | サービス |\n|---|---|")
    quiet = sorted((last_change.get(s, f"{three_years_ago} 以前"), s) for s in alive)
    for date, service in quiet[:args.top]:
        print(f"| {date} | `{service}` |")

    print(f"\n## 直近 12 か月で最も活発なサービス\n\n| API モデル変更コミット数 | サービス |\n|---|---|")
    for service, count in activity.most_common(args.top):
        print(f"| {count} | `{service}` |")


if __name__ == "__main__":
    main()
