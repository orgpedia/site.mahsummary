import datetime
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from dateutil import tz

ListmonkURL = "https://rainbow-mackerel.pikapod.net"
LoginStr = os.environ.get("LISTMONK_LOGIN")  # user_name:password
# LoginStr = "noop:noop"


def get_lists():
    cmd = ["curl", "-s", "-u", f"{LoginStr}"]
    cmd += ["-X", "GET", f"{ListmonkURL}/api/lists?page=1&per_page=100"]

    output = subprocess.check_output(cmd)
    list_json = json.loads(output)
    return list_json["data"]["results"]


def create_campaign(subject, list_ids, markdown_file):
    now = datetime.datetime.now()
    now += datetime.timedelta(minutes=2)
    campaign_time = now.astimezone(tz.tzlocal()).isoformat()

    campaign_dict = {
        "name": subject,
        "subject": subject,
        "lists": list_ids,
        "type": "regular",
        "body": markdown_file.read_text(),
        "content_type": "markdown",
        "send_at": campaign_time,
    }

    cmd = ["curl", "-s", "-u", f"{LoginStr}"]
    cmd += [f"{ListmonkURL}/api/campaigns", "-X", "POST"]
    cmd += ["-H", "Content-Type: application/json;charset=utf-8"]
    cmd += ["--data-raw", json.dumps(campaign_dict)]

    output = subprocess.check_output(cmd)
    result_dict = json.loads(output)

    campaign_id = result_dict["data"]["id"]
    assert result_dict["data"]["status"] == "draft"
    return campaign_id


def run_campaign(campaign_id):
    cmd = ["curl", "-s", "-u", f"{LoginStr}"]
    cmd += ["-X", "PUT", f"{ListmonkURL}/api/campaigns/{campaign_id}/status"]
    cmd += ["-H", "Content-Type: application/json"]
    cmd += ["--data-raw", '{"status": "scheduled"}']
    output = subprocess.check_output(cmd)
    return output


def main(markdown_dir):
    lists = get_lists()
    print(f"# Lists: {len(lists)}")

    campaign_ids = []
    for list in lists:
        list_id, list_name = list["id"], list["name"]
        markdown_file = markdown_dir / f"{list_name.replace(' ','')}.md"
        if not markdown_file.exists():
            print(f"Unable to locate {markdown_file.name}, skipping")
            continue

        print(list_id, list_name)

        subject = f"{list_name} GRs"
        campaign_id = create_campaign(subject, [list_id], markdown_file)
        campaign_ids.append(campaign_id)

    print(f"Generated campaigns: {len(campaign_ids)}, waiting")
    time.sleep(2)

    for campaign_id in campaign_ids:
        print(f"Starting campaign: {campaign_id}")
        run_campaign(campaign_id)


main(Path(sys.argv[1]))
