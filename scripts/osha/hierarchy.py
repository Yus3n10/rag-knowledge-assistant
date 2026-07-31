import re

GROUP_PATTERN = re.compile(r"\([^)]*\)")
HEADING_MAX_CHARS = 120


def ancestor_ids(paragraph_id):
    base = paragraph_id.split("(")[0]
    groups = GROUP_PATTERN.findall(paragraph_id)
    return [base + "".join(groups[:i]) for i in range(len(groups))]


def attach_parent_headings(records):
    by_id = {r["paragraph_id"]: r for r in records}
    for record in records:
        headings = []
        for ancestor in ancestor_ids(record["paragraph_id"]):
            parent = by_id.get(ancestor)
            if parent is None:
                continue
            headings.append({
                "paragraph_id": ancestor,
                "text": parent["text"][:HEADING_MAX_CHARS],
            })
        record["parent_headings"] = headings
    return records
