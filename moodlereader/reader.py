import zipfile, tarfile
import tempfile
import untangle
import os, re, urllib

FILE_PREFIX = "@@PLUGINFILE@@"
FILE_PLUGIN_REGEX = re.compile(FILE_PREFIX + r"[\/|\w|\%|\.]*")

class MoodleBackupReader:
    def __init__(self, filename):
        self.filename = filename
        self.tmpdir = None

    def open(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        
        try:
            with zipfile.ZipFile(self.filename, "r") as zipref:
                zipref.extractall(self.tmpdir.name)
        except zipfile.BadZipFile:
            tar = tarfile.open(self.filename, "r:gz")
            tar.extractall(self.tmpdir.name)
            tar.close()

    def read(self):
        mainfest = os.path.join(self.tmpdir.name, "moodle_backup.xml")
        data = untangle.parse(mainfest).moodle_backup.information.contents

        self.activities = {
            activity.moduleid.cdata: {
                "module": activity.moduleid.cdata,
                "section": activity.sectionid.cdata,
                "module_name": activity.modulename.cdata,
                "title": activity.title.cdata,
                "directory": activity.directory.cdata
            }
            for activity in data.activities.children
        }

        self.sections = {
            section.sectionid.cdata: {
                "id": section.sectionid.cdata,
                "title": section.title.cdata,
                "directory": section.directory.cdata
            }
            for section in data.sections.children
        }

        self.section_ids = [
            section.sectionid.cdata
            for section in data.sections.children
        ]

        self.load_sections()
        self.load_activities()
        self.load_files()

    def _parse_file_references(self, html):
        return re.findall(FILE_PLUGIN_REGEX, html)

    def _parse_book(self, name, activity_dir):
        filename = os.path.join(activity_dir, "book.xml")
        data = untangle.parse(filename).activity
        chapters = []

        output = {
            "id": data["id"],
            "name": data.book.name.cdata,
            "intro": data.book.intro.cdata,
            "introformat": int(data.book.introformat.cdata),
            "chapters": chapters
        }

        for chapter in data.book.chapters.children:
            chapter_data = {
                "id": chapter["id"],
                "title": chapter.title.cdata,
                "content": chapter.content.cdata,
                "contentformat": int(chapter.contentformat.cdata)
            }

            refs = []
            if chapter_data["contentformat"] == 1:
                refs.extend(self._parse_file_references(chapter_data["content"]))

            chapter_data.update({
                "files": refs
            })

            chapters.append(chapter_data)
        
        return output

    def _parse_page(self, name, activity_dir):
        filename = os.path.join(activity_dir, "page.xml")
        data = untangle.parse(filename).activity
        refs = []

        output = {
            "id": data["id"],
            "name": data.page.name.cdata,
            "intro": data.page.intro.cdata,
            "introformat": int(data.page.introformat.cdata),
            "content": data.page.content.cdata,
            "contentformat": int(data.page.contentformat.cdata),
            "files": refs
        }


        if output["introformat"] == 1:
            refs.extend(self._parse_file_references(output["intro"]))
        
        if output["contentformat"] == 1:
            refs.extend(self._parse_file_references(output["content"]))

        return output

    def _parse_resource(self, name, activity_dir):
        filename = os.path.join(activity_dir, "resource.xml")
        data = untangle.parse(filename).activity
        refs = []

        output = {
            "id": data["id"],
            "name": data.resource.name.cdata,
            "intro": data.resource.intro.cdata,
            "introformat": int(data.resource.introformat.cdata),
            "contextid": data["contextid"]
        }

        return output

    def _parse_activity(self, name, activity_dir):
        activity_type = name.split('_')[0]

        output = {
            "type": activity_type
        }

        if activity_type == 'page':       
            output.update(self._parse_page(name, activity_dir))
        elif activity_type == 'book':
            output.update(self._parse_book(name, activity_dir))
        elif activity_type == 'resource':
            output.update(self._parse_resource(name, activity_dir))
        else:
            filename = os.path.join(activity_dir, activity_type + ".xml")
            try:
                data = untangle.parse(filename)
                if hasattr(data.activity, name):
                    module = getattr(data.activity, name, None)

                    if module is not None:
                        output.update({
                            "name": module.name.cdata,
                            "intro": module.intro.cdata,
                            "introformat": int(module.introformat.cdata),
                        })

                output.update({
                    "id": data.activity["id"]
                })
            except:
                output.update({
                    "error": "Unable to parse " + activity_type
                })

        return output        

    def _parse_section(self, section_dir):
        filename = os.path.join(section_dir, "section.xml")
        data = untangle.parse(filename)

        seq = data.section.sequence.cdata.split(",")

        if len(seq) == 1 and seq[0] == "":
            seq = []
        
        section_data = {
            "id": data.section["id"],
            "summary": data.section.summary.cdata,
            "format": int(data.section.summaryformat.cdata),
            "sequence": seq,
            "visible": data.section.visible.cdata == "1",
            "name": data.section.name.cdata
        }

        files = []
        if section_data["format"] == 1:
            files.extend(self._parse_file_references(section_data["summary"]))

        section_data["files"] = files

        return section_data

    def load_sections(self):
        for section_id, section in self.sections.items():
            dirname = os.path.join(self.tmpdir.name, section["directory"])
            self.sections[section_id].update(
                self._parse_section(dirname)
            )

    def load_activities(self):
        for module_id, activity in self.activities.items():
            dirname = os.path.join(self.tmpdir.name, activity["directory"])
            self.activities[module_id].update(
                self._parse_activity(
                    activity["module_name"], dirname
                )
            )

    def load_files(self):
        filename = os.path.join(self.tmpdir.name, "files.xml")
        data = untangle.parse(filename)
        output = {}
        file_context = {}
        for f in data.files.children:
            content_hash = f.contenthash.cdata
            hash_prefix = content_hash[:2]
            filename = os.path.join(self.tmpdir.name, hash_prefix, content_hash)
            file_data = {
                "id": f["id"],
                "contextid": f.contextid.cdata,
                "path": f.filepath.cdata,
                "name": f.filename.cdata,
                "mimetype": f.mimetype.cdata,
                "filename": filename
            }


            file_url = urllib.parse.urljoin(file_data["path"], urllib.parse.quote(file_data["name"]))

            file_context[file_data["contextid"]] = FILE_PREFIX + file_url
            file_data["url"] = file_url

            print(FILE_PREFIX + file_url, file_data)

            output[FILE_PREFIX + file_url] = file_data
        
        self.files = output
        self.file_contexts = file_context


    def close(self):
        self.tmpdir.cleanup()
        
