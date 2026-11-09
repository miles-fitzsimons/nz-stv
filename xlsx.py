import re
import sys
import zipfile
import xml.etree.ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def column_index(ref):
    letters = re.match(r"[A-Z]+", ref).group()
    index = 0
    for letter in letters:
        index = index * 26 + ord(letter) - 64
    return index - 1


def shared_strings(archive):
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")) for si in root.findall("m:si", NS)]


def sheets(path):
    with zipfile.ZipFile(path) as archive:
        strings = shared_strings(archive)
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {rel.get("Id"): rel.get("Target") for rel in rels.iter(f"{REL_NS}Relationship")}
        result = {}
        for sheet in workbook.find("m:sheets", NS):
            target = targets[sheet.get(f"{{{NS['r']}}}id")].lstrip("/")
            target = target if target.startswith("xl/") else f"xl/{target}"
            root = ET.fromstring(archive.read(target))
            rows = []
            for row in root.iter(f"{{{NS['m']}}}row"):
                cells = {}
                for cell in row.findall("m:c", NS):
                    kind = cell.get("t")
                    value_node = cell.find("m:v", NS)
                    if kind == "inlineStr":
                        value = "".join(t.text or "" for t in cell.iter(f"{{{NS['m']}}}t"))
                    elif value_node is None:
                        continue
                    elif kind == "s":
                        value = strings[int(value_node.text)]
                    else:
                        value = value_node.text
                    cells[column_index(cell.get("r"))] = value
                if cells:
                    rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
            result[sheet.get("name")] = rows
        return result


if __name__ == "__main__":
    for name, rows in sheets(sys.argv[1]).items():
        print(f"=== sheet {name!r}: {len(rows)} rows")
        for row in rows[: int(sys.argv[2]) if len(sys.argv) > 2 else 40]:
            print(row)
