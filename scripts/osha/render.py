def render_subpart_markdown(subpart_name, sections):
    lines = [f"# {subpart_name}", ""]
    for section in sections:
        lines.append(f"## {section['section_id']} - {section['section_heading']}")
        lines.append("")
        for record in section["records"]:
            lines.append(f"**{record['paragraph_id']}**")
            lines.append("")
            lines.append(record["text"])
            lines.append("")
            for table in record["tables"]:
                lines.append(table)
                lines.append("")
    return "\n".join(lines)
