from moodlereader import MoodleBackupReader, FILE_PREFIX

def update_html_refs(prefix, html, file_refs, files):
    for file_ref in file_refs:
        html = html.replace(file_ref, prefix + files[file_ref]["url"])
    return html

reader = MoodleBackupReader("moodlebackup.mbz")

reader.open()
reader.read()

sections = reader.sections
section_ids = reader.section_ids
activities = reader.activities
files = reader.files
file_contexts = reader.file_contexts


url_prefix = "https://www.openlearning.com/courses/my_course"
pages = {}
for module_id, activity in activities.items():
    blocks = []

    is_missing = False
    if activity["type"] == "page":
        blocks.append({
            "html": update_html_refs(url_prefix, activity["content"], activity["files"], files),
        })
    elif activity["type"] == "book":
        for chapter in activity["chapters"]:
            blocks.append({
                "html": update_html_refs(url_prefix, chapter["content"], chapter["files"], files),
                "title": chapter["title"],
            })
    elif activity["type"] == "resource":
        print(file_contexts[activity["contextid"]])
        blocks.append({
            "title": activity["name"],
            "file": update_html_refs(
                url_prefix,
                file_contexts[activity["contextid"]],
                file_contexts[activity["contextid"]],
                files
            )
        })
    else:
        is_missing = True

    if is_missing and "id" in activity:
        pages[module_id] = {
            "title": activity["title"],
            "name": activity["module_name"] + " not imported",
            "blocks": [],
            "intro": ""
        }
    elif not is_missing:
        pages[module_id] = {
            "title": activity["title"],
            "name": activity["name"],
            "blocks": blocks,
            "intro": activity["intro"]
        }

modules = []
missing = {
    "title": "Missing content",
    "name": "Missing content",
    "blocks": [],
    "intro": ""
}
for section_id in section_ids:
    section = sections[section_id]
    modules.append({
        "title": section["title"],
        "html": update_html_refs(url_prefix, section["summary"], section["files"], files),
        "pages": [
            pages.get(key, missing) for key in section.get("sequence")
        ]
    })

import json
print(json.dumps(modules, indent=2))

reader.close()
