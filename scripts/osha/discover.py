import re

SECTION_LINK_PATTERN = re.compile(r"standardnumber/1910/(1910\.\d+)")


def section_ids_from_subpart(html):
    found = set(SECTION_LINK_PATTERN.findall(html))
    return sorted(found, key=lambda s: int(s.split(".")[1]))
