import datetime
import gzip
import json
import re
import sys
from operator import itemgetter
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from more_itertools import first, flatten

DistrictNames = [
    "Ahmednagar",
    "Akola",
    "Amravati",
    "Aurangabad",
    "Beed",
    "Bhandara",
    "Buldhana",
    "Chandrapur",
    "Dhule",
    "Gadchiroli",
    "Gondia",
    "Hingoli",
    "Jalgaon",
    "Jalna",
    "Kolhapur",
    "Latur",
    "Mumbai_City",
    "Mumbai_Suburban",
    "Nagpur",
    "Nanded",
    "Nandurbar",
    "Nashik",
    "Osmanabad",
    "Palghar",
    "Parbhani",
    "Pune",
    "Raigad",
    "Ratnagiri",
    "Sangli",
    "Satara",
    "Sindhudurg",
    "Solapur",
    "Thane",
    "Wardha",
    "Washim",
    "Yavatmal",
]

DeptListIDs = {
    "Environment Department": 7,
    "Finance Department": 8,
    "Food, Civil Supplies and Consumer Protection Department": 9,
    "General Administration Department": 10,
    "Higher and Technical Education Department": 11,
    "Home Department": 12,
    "Housing Department": 13,
    "Industries, Energy and Labour Department": 14,
    "Information Technology Department": 15,
    "Law and Judiciary Department": 16,
    "Marathi Language Department": 17,
    "Medical Education and Drugs Department": 18,
    "Minorities Development Department": 19,
    "Other Backward Bahujan Welfare Department": 20,
    "Parliamentary Affairs Department": 21,
    "Persons with Disabilities Welfare Department": 22,
    "Planning Department": 23,
    "Public Health Department": 24,
    "Public Works Department": 25,
    "Revenue and Forest Department": 26,
    "Rural Development Department": 27,
    "School Education and Sports Department": 28,
    "Skill Development and Entrepreneurship Department": 29,
    "Social Justice and Special Assistance Department": 30,
    "Soil and Water Conservation Department": 31,
    "Tourism and Cultural Affairs Department": 32,
    "Tribal Development Department": 33,
    "Urban Development Department": 34,
    "Water Resources Department": 35,
    "Water Supply and Sanitation Department": 36,
    "Women and Child Development Department": 37,
    "Agriculture, Dairy Development, Animal Husbandry and Fisheries Department": 5,
    "Co-operation, Textiles and Marketing Department": 6,
}


def build_dept_summary(doc_infos):
    doc_info_dict = {}
    for doc_info in doc_infos:
        doc_info_dict.setdefault(doc_info["dept"], []).append(doc_info)

    return doc_info_dict


def build_district_summary(doc_infos):
    doc_info_dict = {}
    for district_name in DistrictNames:
        d = district_name
        d = d.replace("_City", "")
        doc_info_dict[d] = []

        # Find all documents that belong to a district
        district_infos = []
        for doc_info in doc_infos:
            if "districts" in doc_info and d in doc_info["districts"]:
                district_infos.append(doc_info)

        if len(district_infos) <= 10:
            doc_info_dict[d] = district_infos
        else:
            # Score the documents to select top 10
            def score_info(doc_info):
                score = doc_info["district_counts"][d] / len(doc_info["district_counts"])
                return score

            di_sorted = sorted(district_infos, key=score_info, reverse=True)
            doc_info_dict[d] = di_sorted[:10]

    return doc_info_dict


def annotate_doc_infos(gr_dir, doc_infos):
    def extract_money2(doc_text):
        # r'Rs\.\s*(?:[\d,]+\s*)+\S+'
        pattern = r"(?:(?:Rs\.\s)?\d+(?:\.\d+)?\s(?:crore|lakhs))|\b\d+\b"
        amounts = [re.findall(pattern, ln.replace(",", "")) for ln in doc_text.split("\n")]
        amounts = list(flatten(amounts))

        for m in ["crore", "lakh"]:
            m_amounts = [a for a in amounts if m in a]
            f_amounts = [a.replace("Rs.", "").replace(m, "") for a in m_amounts]
            mf_amounts = sorted(zip(m_amounts, f_amounts), key=itemgetter(1))
            if mf_amounts:
                return mf_amounts[-1][0]
        return None

    def extract_money(doc_text):
        doc_text = doc_text.replace("lacs", "lakhs").replace("/-Crore", " crore")

        pattern = r"Rs\.\s?(?:(?:\d{1,8}(?:,\d{3})*|\d+)(?:\.\d{1,8})?)\s?(?:lakh|crore)?"
        amounts = re.findall(pattern, doc_text)

        # return the highest value
        for m in ["crore", "lakh"]:
            m_amounts = [a for a in amounts if m in a]
            f_amounts = [a.replace("Rs.", "").replace(m, "") for a in m_amounts]
            mf_amounts = sorted(zip(m_amounts, f_amounts), key=itemgetter(1))
            if mf_amounts:
                return mf_amounts[-1][0]

    def split_doc(doc_path):
        year = doc_path.name[:4]
        doc_text = doc_path.read_text()
        doc_lines = [ln for ln in doc_text.split("\n") if ln and ln[0] != "#"]

        year_strs = [f" {year}", f".{year}", f"/{year}"]

        sub_end_idx, body_start_idx = 0, 0
        for idx, line in enumerate(doc_lines[:10]):
            if "Government" in line and "Maharashtra" in line:
                sub_end_idx = idx

            if any(y in line for y in year_strs) and (
                "date" in line.lower() or "as of" in line.lower()
            ):
                body_start_idx = idx

        sub_end_idx = 2 if sub_end_idx == 0 else sub_end_idx
        body_start_idx = 8 if body_start_idx == 0 else body_start_idx

        return "\n".join(doc_lines[:sub_end_idx]), "\n".join(doc_lines[body_start_idx:])

    def find_districts(input_path, district_names):
        district_names = [d.replace(" City", "") for d in district_names]
        # We split doc to ensure that Mumbai which is there in every addres is not counted
        # easier way would be to reduce the count of Mumbai by 1 !!
        doc_subject, doc_body = split_doc(input_path)
        district_counts = {}
        for d in district_names:
            cnt = doc_subject.count(d) + doc_body.count(d)
            if cnt:
                district_counts[d] = cnt
        return district_counts

    def find_subject(doc_path):
        lines = [ln for ln in doc_path.read_text().split("\n") if ln and ln[0] != "#"]
        line_idx = 0
        for idx, line in enumerate(lines):
            line = line.strip(" .,").lower()
            if (
                line.startswith("the government of maharashtra")
                or line.startswith("government of maharashtra")
                or line.startswith("the maharashtra government")
                or line.startswith("| the government of maharashtra")
            ):
                line_idx = idx
                break

            if line.endswith("government of maharashtra") or line.endswith("maharashtra govt"):
                line_idx = idx + 1
                break

            if idx > 10:
                line_idx = 1
                print(f"Unable to find govt of maharashtra in {doc_path}")
                break

        mr_doc_path = doc_path.parent / doc_path.name.replace(".en.", ".mr.")
        mr_lines = [ln for ln in mr_doc_path.read_text().split("\n") if ln and ln[0] != "#"]
        mr_subject = " ".join(mr_lines[:line_idx])
        return mr_subject

    district_names = [d.replace("_", " ") for d in DistrictNames]

    result_doc_infos = []
    for doc_info in doc_infos:
        if doc_info["dept"] == "Soil & Water Conservation Department":
            doc_info["dept"] = "Soil and Water Conservation Department"

        doc_path = (
            gr_dir / Path(doc_info["dept"].replace(" ", "_")) / f'{doc_info["code"]}.pdf.en.txt'
        )
        if not doc_path.exists():
            continue

        doc_text = doc_path.read_text()
        doc_text_lower = doc_text.lower()

        doc_info["en_doc_path"] = doc_path

        funds_amount = None
        if any(m in doc_text for m in ["crore", "lakh", "lacs"]):
            doc_type = "Funds"

            funds_amount = extract_money(doc_text)
            if not funds_amount:
                print(f"Unable to find funds in {doc_info['en_doc_path']}")

        elif any(p in doc_text_lower for p in ["posting", "transfer", "seniority", "temporary"]):
            doc_type = "Personnel"
        else:
            doc_type = "Miscellaneous"

        doc_info["doc_type"] = doc_type
        doc_info["funds_amount"] = funds_amount
        doc_info["district_counts"] = find_districts(doc_path, district_names)

        dist_counts = doc_info["district_counts"]
        if len(dist_counts) > 5:
            dist_counts = dict(
                ((d, c) for idx, (d, c) in enumerate(dist_counts.items()) if idx < 5)
            )
            doc_info["districts"] = ", ".join(d for (d, c) in dist_counts.items())
            doc_info["districts"] += ", ..."
        else:
            doc_info["districts"] = ", ".join(d for (d, c) in dist_counts.items())

        doc_info["mr_text"] = find_subject(doc_path)
        result_doc_infos.append(doc_info)

    return result_doc_infos


class DeptInfo:
    def __init__(self, name, dept_info_dict):
        for k, v in dept_info_dict.items():
            setattr(self, k, v)


class SiteInfo:
    def __init__(self, site_info):
        for k, v in site_info.items():
            setattr(self, k, v)

    # so that we can get date_str also in specified languages
    def set_date(self, dt, lang):
        if not dt:
            self.week_num = ""
            self.start_date_str = ""
            self.end_date_str = ""
            return

        self.year = dt.year
        self.week_num = dt.isocalendar()[1]
        week_str = f"{dt.year}-W{self.week_num}"

        start_date = datetime.datetime.strptime(week_str + "-1", "%Y-W%W-%w").date()
        end_date = start_date + datetime.timedelta(days=5)

        self.start_date_str = start_date.strftime("%d %B %Y")
        self.end_date_str = end_date.strftime("%d %B %Y")

        if lang != "en":
            self.start_date_str = convert_date_str(self.start_date_str, self)
            self.end_date_str = convert_date_str(self.end_date_str, self)
            self.year = convert_num(self.year, self)
            self.week_num = convert_num(self.week_num, self)


def convert_num(d, site_info):
    r = []
    for c in str(d):
        t = getattr(site_info, c) if c not in ".," else c
        r.append(t)
    return "".join(r)


def convert_money(m, site_info):
    m = m.lower().strip() if m else m
    if not m:
        return ""

    if "rs." in m and "rs. " not in m:
        m = m.replace("rs.", "rs. ")

    for s in ["rs.", "lakhs", "crores", "lakh", "crore"]:
        m = m.replace(s, getattr(site_info, s))

    num_str = first(n for n in m.split() if n.replace(",", "").replace(".", "").isdigit())
    m = m.replace(num_str, convert_num(num_str, site_info))
    return m


def convert_date_str(date_str, site_info):
    d, m, y = date_str.split()
    return f"{convert_num(d, site_info)} {getattr(site_info, m)} {convert_num(y, site_info)}"


class DocInfo:
    def __init__(self, doc_info, site_info, lang="en"):
        for k, v in doc_info.items():
            setattr(self, k, v)

        self.lang = lang
        self.site_info = site_info
        self.en_dept = self.dept.replace(" ", "_")
        self.num_pages = 3

        if lang != "en":
            self.text = self.mr_text
            if self.districts:
                dists = self.districts.split(",")
                dists = [dists] if isinstance(dists, str) else dists
                self.districts = ", ".join(getattr(site_info, d.strip()) for d in dists)

            self.num_pages = convert_num(self.num_pages, site_info)
            self.doc_type = getattr(site_info, self.doc_type)
            self.funds_amount = convert_money(self.funds_amount, site_info)
            self.dept = getattr(site_info, self.dept)

    @property
    def date_str(self):
        date_str = self.date.strftime("%d %b %Y")
        if self.lang != "en":
            date_str = convert_date_str(date_str, self.site_info)
        return date_str


SiteInfoGlobal = None


def get_site_info(lang):
    global SiteInfoGlobal
    # TODO, get rid of this load it only once and pass

    if not SiteInfoGlobal:
        SiteInfoGlobal = yaml.load(Path("conf/site.yml").read_text(), Loader=yaml.FullLoader)

    input_dict = {"lang_selected": lang, "lang": lang, lang: "selected"}

    for key, key_dict in SiteInfoGlobal.items():
        input_dict[key] = key_dict[lang]
    return SiteInfo(input_dict)


def gen_index_html(output_dir, lang, jinja_env):
    if lang == "en":
        template = jinja_env.get_template("index.html")
    else:
        template = jinja_env.get_template(f"index-{lang}.html")

    site_info = get_site_info(lang)
    site_info.title = site_info.mahGRs
    site_info.doc_type = "common"

    html_file = output_dir / Path(f"{lang}/index.html")
    html_file.write_text(template.render(site=site_info))


def gen_dept_top_html(output_dir, dept_names, doc_infos_dict, lang, stub, jinja_env):
    def get_url(name, lang):
        return f"{stub}-{name.replace(' ','')}.html"

    def get_date(doc_infos_dict):
        first_info = first(flatten(doc_infos_dict.values()), default=None)
        if first_info:
            return first_info["date"]

    template = jinja_env.get_template("top-level.html")
    site_info = get_site_info(lang)
    site_info.set_date(get_date(doc_infos_dict), lang)
    site_info.title = site_info.dept_title
    site_info.doc_type = "top-department"

    dept_infos = [
        (
            getattr(site_info, name),
            get_url(name, lang),
            convert_num(len(doc_infos_dict.get(name, [])), site_info),
        )
        for name in dept_names
    ]

    html_file = output_dir / Path(f"{lang}/dept/{stub}-summary.html")
    html_file.write_text(template.render(site=site_info, depts=dept_infos))

    html_file = output_dir / Path(f"{lang}/dept/summary.html")
    html_file.write_text(template.render(site=site_info, depts=dept_infos))


def gen_district_top_html(output_dir, district_names, doc_infos_dict, lang, stub, jinja_env):
    def get_url(name, lang):
        return f"{stub}-{name.replace(' ','')}.html"

    def get_date(doc_infos_dict):
        first_info = first(flatten(doc_infos_dict.values()), default=None)
        if first_info:
            return first_info["date"]

    template = jinja_env.get_template("top-level.html")
    site_info = get_site_info(lang)
    site_info.set_date(get_date(doc_infos_dict), lang)
    site_info.doc_type = "top-district"

    site_info.title = site_info.district_title
    district_infos = [
        (
            getattr(site_info, name),
            get_url(name, lang),
            convert_num(len(doc_infos_dict.get(name, [])), site_info),
        )
        for name in district_names
    ]

    html_file = output_dir / Path(f"{lang}/dist/{stub}-summary.html")
    html_file.write_text(template.render(site=site_info, depts=district_infos))

    html_file = output_dir / Path(f"{lang}/dist/summary.html")
    html_file.write_text(template.render(site=site_info, depts=district_infos))


def gen_dept_summary_html(output_dir, dept_name, doc_infos, lang, stub, jinja_env):
    site_info = get_site_info(lang)

    # Ensure the docs come in this order only, across languages
    result_doc_dict = {site_info.Funds: [], site_info.Personnel: [], site_info.Miscellaneous: []}

    doc_infos.sort(key=itemgetter("doc_type"))
    for doc_info_dict in doc_infos:
        doc_info = DocInfo(doc_info_dict, site_info, lang)
        result_doc_dict.setdefault(doc_info.doc_type, []).append(doc_info)

    result_doc_dict = dict((k, v) for (k, v) in result_doc_dict.items() if v)

    template = jinja_env.get_template("summary.html")

    site_info.set_date(doc_infos[0]["date"], lang)
    site_info.title = f"{site_info.weekly_summary}: {getattr(site_info, dept_name)}"

    site_info.doc_type = "department"
    site_info.item_name = getattr(site_info, dept_name)
    site_info.list_id = DeptListIDs[dept_name]

    dept_file_name = dept_name.replace(" ", "")
    html_file = output_dir / Path(f"{lang}/dept/{stub}-{dept_file_name}.html")
    html_file.write_text(
        template.render(site=site_info, dept_name=dept_name, depts=result_doc_dict)
    )


def gen_dept_summary_md(output_dir, dept_name, doc_infos, lang, stub, jinja_env):
    result_doc_dict = {}
    site_info = get_site_info(lang)

    doc_infos.sort(key=itemgetter("doc_type"))
    for doc_info_dict in doc_infos:
        doc_info = DocInfo(doc_info_dict, site_info, lang)
        result_doc_dict.setdefault(doc_info.doc_type, []).append(doc_info)

    template = jinja_env.get_template("summary.md")

    site_info.set_date(doc_infos[0]["date"], lang)
    site_info.title = f"{getattr(site_info, dept_name)}"
    site_info.doc_type = "department"
    site_info.item_name = getattr(site_info, dept_name)

    if lang == "en":
        dept_file_name = dept_name.replace(" ", "")
        md_file = output_dir / Path(f"{lang}/dept/{dept_file_name}.md")
        md_file.write_text(
            template.render(site=site_info, dept_name=dept_name, depts=result_doc_dict)
        )


def gen_district_summary_html(output_dir, district_name, doc_infos, lang, stub, jinja_env):
    site_info = get_site_info(lang)
    result_doc_dict = {}
    doc_infos.sort(key=itemgetter("dept"))
    for doc_info_dict in doc_infos:
        doc_info = DocInfo(doc_info_dict, site_info, lang)
        result_doc_dict.setdefault(doc_info.dept, []).append(doc_info)

    template = jinja_env.get_template("summary.html")

    site_info.set_date(doc_infos[0]["date"], lang)
    site_info.title = (
        f"{site_info.weekly_summary}: {getattr(site_info, district_name)} {site_info.district}"
    )
    site_info.doc_type = "district"
    site_info.item_name = getattr(site_info, district_name)
    site_info.list_id = DeptListIDs.get(district_name, -1)

    district_file_name = district_name.replace(" ", "")

    html_file = output_dir / Path(f"{lang}/dist/{stub}-{district_file_name}.html")
    html_file.write_text(
        template.render(site=site_info, dept_name=district_name, depts=result_doc_dict)
    )


def gen_subscription(output_dir, lang, jinja_env):
    if lang != "en":
        return

    site_info = get_site_info(lang)
    template = jinja_env.get_template("subscription.html")
    html_file = output_dir / f"{lang}/subscription.html"
    html_file.write_text(template.render(site=site_info))


def gen_archive_html(output_dir, lang, jinja_env):
    def build_dict(paths):
        r = {}
        for p in paths:
            y, w, _ = p.name.split("-")
            w = w[1:]
            if lang != "en":
                y = convert_num(y, site_info)
                w = convert_num(w, site_info)
            r.setdefault(y, []).append(w)
        return r

    def year_week(path):
        y, w, _ = path.name.split("-")
        return (int(y), int(w[1:]))

    site_info = get_site_info(lang)
    site_info.title = site_info.archive_title
    site_info.doc_type = "common"

    dept_archive_paths = list((output_dir / Path(f"{lang}/dept/")).glob("*-summary.html"))
    dept_archive_paths.sort(key=year_week)
    dept_archive = build_dict(dept_archive_paths)

    dist_archive_paths = list((output_dir / Path(f"{lang}/dist/")).glob("*-summary.html"))
    dist_archive_paths.sort(key=year_week)
    dist_archive = build_dict(dist_archive_paths)

    template = jinja_env.get_template("archive.html")

    html_file = output_dir / Path(f"{lang}/archive.html")
    html_file.write_text(
        template.render(site=site_info, dept_archive=dept_archive, district_archive=dist_archive)
    )


def get_week_document_infos(gr_dir, year, wk_num):
    doc_infos = list(flatten(json.loads(f.read_text()).values() for f in gr_dir.glob("*/GRs.json")))
    [
        i.__setitem__("date", datetime.datetime.strptime(i["date"], "%d-%m-%Y").date())
        for i in doc_infos
    ]

    if wk_num == -1:
        max_date = max((i["date"] for i in doc_infos), default=None)
        if not max_date:
            return []
        wk_num = max_date.isocalendar()[1]

    doc_infos = [
        i for i in doc_infos if i["date"].isocalendar()[1] == wk_num and i["date"].year == year
    ]
    return doc_infos, year, wk_num


def get_searchdoc_dict(doc_info):
    doc = {}
    doc["idx"] = doc_info["code"]
    doc["short_idx"] = f'{doc_info["code"][:9]}...'
    doc["text"] = doc_info["text"]
    doc["districts"] = doc_info["districts"] if doc_info.get("districts", None) else ""
    doc["date"] = doc_info["date"].strftime("%d %B %Y")
    doc["url"] = doc_info["url"]
    doc["num_pages"] = 3  # doc_info['num_pages'] TODO PLEASE CHANGE
    doc["doc_type"] = doc_info["doc_type"] if doc_info.get("doc_type", None) else ""
    doc["funds_amount"] = doc_info["funds_amount"] if doc_info.get("funds_amount", None) else ""
    doc["dept"] = doc_info["dept"]
    return doc


def write_search_index(output_dir, new_doc_infos):
    def read_gz_json(json_gz_file):
        with gzip.open(json_gz_file, "rb") as f:
            json_obj = json.loads(f.read())
        return json_obj

    def write_gz_json(json_gz_file, json_obj):
        with gzip.open(json_gz_file, "wb") as f:
            f.write(bytes(json.dumps(json_obj, separators=(",", ":")), encoding="utf-8"))
    
    from lunr import lunr

    new_search_dicts = [get_searchdoc_dict(i) for i in new_doc_infos]

    docs_file = output_dir / "docs.json.gz"
    if docs_file.exists():
        old_search_dicts = read_gz_json(docs_file)
        old_idxs = set(d["idx"] for d in old_search_dicts)
        new_search_dicts = [d for d in new_search_dicts if d["idx"] not in old_idxs]

        search_dicts = old_search_dicts + new_search_dicts
    else:
        search_dicts = new_search_dicts

    lunrIdx = lunr(ref="idx", fields=["text", "dept"], documents=search_dicts)

    search_index_file = output_dir / "lunr.idx.json"
    write_gz_json(search_index_file, lunrIdx.serialize())
    
    #search_index_file.write_text(json.dumps(lunrIdx.serialize(), separators=(",", ":")))

    docs_file = output_dir / "docs.json.gz"
    #docs_file.write_text(json.dumps(search_dicts, separators=(",", ":")))
    write_gz_json(docs_file, search_dicts)


# This creates a minfied index and docs file, but also additional work on frontend to
# convert all the numbers pto string, better savings can be obtained by
# compressing as even after afer minifying the 10MB files goes to 6 MB
# lnur.idx.json file is pretty verbose, need to trim that as well.

"""
Before mnifying but compressing
(build-DJwq3dbw-py3.7) ~/orgpedia/mahsummary/docs:$ls -lh *.gz
-rw-r--r--  1 mukund  staff   993K Nov  3 16:44 docs.json.gz
-rw-r--r--  1 mukund  staff   2.5M Nov  3 14:57 lunr.idx.json.gz

After mnifying and compressing
(build-DJwq3dbw-py3.7) ~/orgpedia/mahsummary/docs:$ls -lh *.gz
-rw-r--r--  1 mukund  staff   877K Nov  3 17:12 docs.json.gz
-rw-r--r--  1 mukund  staff   1.6M Nov  3 17:12 lunr.idx.json.gz

# NOT MUCH SAVINGS
"""


def write_search_index_minify(output_dir, new_doc_infos):
    def get_searchdoc_dict(doc_info, doc_idx):
        doc = {}
        doc["idx"] = doc_idx
        doc["code"] = doc_info["code"]
        doc["text"] = doc_info["text"]

        districts = doc_info.get("districts", "").strip("., ").split(",")
        district_nums = [districts_dict[d.strip().replace(" ", "_")] for d in districts if d]

        doc["districts"] = district_nums
        doc["num_pages"] = 3  # doc_info['num_pages']  # PLEASE CHANGE THIS
        doc["doc_type"] = doc_type_dict[doc_info.get("doc_type", "Unknown")]
        doc["funds_amount"] = doc_info["funds_amount"] if doc_info.get("funds_amount", None) else ""
        doc["dept_num"] = dept_dict[doc_info["dept"]]
        doc["dept"] = doc_info["dept"]
        return doc

    from lunr import lunr

    docs_file = output_dir / "docs.json"

    doc_type_dict = {"Funds": 0, "Personnel": 1, "Miscellaneous": 2, "Unknown": 3}
    dept_dict = dict((d, idx) for (idx, d) in enumerate(DeptListIDs.keys()))
    districts_dict = dict((d, idx) for (idx, d) in enumerate(DistrictNames))
    districts_dict["Mumbai"] = len(districts_dict)

    if docs_file.exists():
        old_dicts = json.loads(docs_file.read_text())

        old_codes = set(d["code"] for d in old_dicts)
        new_doc_infos = [i for i in new_doc_infos if i["code"] not in old_codes]

        s_idx = len(old_dicts)
        new_dicts = [get_searchdoc_dict(i, idx + s_idx) for idx, i in enumerate(new_doc_infos)]

        search_dicts = old_dicts + new_dicts
    else:
        search_dicts = [get_searchdoc_dict(i, idx) for idx, i in enumerate(new_doc_infos)]

    lunrIdx = lunr(ref="idx", fields=["text", "dept"], documents=search_dicts)

    search_index_file = output_dir / "lunr.idx.json"
    search_index_file.write_text(json.dumps(lunrIdx.serialize(), separators=(",", ":")))

    docs_file = output_dir / "docs.json"
    [d.pop("dept") for d in search_dicts]
    docs_file.write_text(json.dumps(search_dicts, separators=(",", ":")))


def write_html(week_doc_infos, lang, output_dir, stub, dept_names, district_names):
    dept_doc_infos_dict = build_dept_summary(week_doc_infos)
    district_doc_infos_dict = build_district_summary(week_doc_infos)

    env = Environment(
        loader=FileSystemLoader("conf/templates"),
        autoescape=select_autoescape(),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    gen_archive_html(output_dir, lang, env)
    gen_index_html(output_dir, lang, env)

    gen_subscription(output_dir, lang, env)

    gen_dept_top_html(output_dir, dept_names, dept_doc_infos_dict, lang, stub, env)
    gen_district_top_html(output_dir, district_names, district_doc_infos_dict, lang, stub, env)

    for dept, doc_infos in dept_doc_infos_dict.items():
        if doc_infos:
            gen_dept_summary_html(output_dir, dept, doc_infos, lang, stub, env)
            gen_dept_summary_md(output_dir, dept, doc_infos, lang, stub, env)

    for district, doc_infos in district_doc_infos_dict.items():
        if doc_infos:
            gen_district_summary_html(output_dir, district, doc_infos, lang, stub, env)


StartDate = datetime.date(year=2022, month=8, day=15)


def main():
    if len(sys.argv) < 1:
        print("Usage: {sys.argv[0]} <gr_dir> <output_dir> [last|all] [<langs>]")

    gr_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])

    week_str = sys.argv[3] if len(sys.argv) > 3 else "last"
    assert week_str in ("last", "all"), f"Incorrect {week_str}: valid values last|all"

    lang_str = sys.argv[4] if len(sys.argv) > 4 else "en"
    langs = lang_str.split(",")
    assert all(lg in ["en", "mr"] for lg in langs), f"Incorrect {langs}: valid values mr,en"

    dept_names = sorted(p.name.replace("_", " ") for p in gr_dir.glob("*"))
    district_names = sorted(DistrictNames)

    year_weeks = []
    if week_str == "last":
        year, week_num = datetime.date.today().year, -1
        year_weeks = [(year, week_num)]
    else:
        date, today = StartDate, datetime.date.today()
        while date <= today:
            year_weeks.append((date.year, date.isocalendar()[1]))
            date += datetime.timedelta(days=7)

    all_week_doc_infos = []
    for yr, wk in year_weeks:
        # this gets the last week_num from document infos
        week_doc_infos, year, week_num = get_week_document_infos(gr_dir, yr, wk)
        if not week_doc_infos:
            print(f"Weeknum: {year}-{wk}: No documents found")
            continue

        week_doc_infos = annotate_doc_infos(gr_dir, week_doc_infos)

        stub = f"{year}-W{week_num}"
        for lang in langs:
            write_html(week_doc_infos, lang, output_dir, stub, dept_names, district_names)

        all_week_doc_infos.extend(week_doc_infos)

    if "en" in langs:
        print(f"Search: {len(all_week_doc_infos)}")
        write_search_index(output_dir, all_week_doc_infos)


main()
