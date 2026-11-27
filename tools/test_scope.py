import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from check_scope import ROOT, check_scope, read_pr

class ScopeTests(unittest.TestCase):
    rules = json.loads((ROOT / "collaboration/ownership.json").read_text())
    def test_owned_paths(self):
        for branch, entry in self.rules.items():
            for path in entry["paths"]:
                with self.subTest(branch=branch, path=path):
                    check_scope(self.rules, branch.replace("*","paper"), [path + "x.py" if path.endswith("/") else path])

    def test_shared_and_neighbour_paths_rejected(self):
        for path in ["docs/requirements.md", "frontend/src/design/folio.css",
                     "frontend/src/features/results/Score.jsx","frontend/src/features/delivery-old/Attempt.jsx"]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                check_scope(self.rules, "work/delivery", [path])

    def test_branch_and_scope_required(self):
        for branch, paths in [("unassigned/x", ["docs/pages.md"]), ("work/delivery", []),
                              ("foundation/x", ["backend/app/features/results/grade.py"])]:
            with self.subTest(branch=branch), self.assertRaises(ValueError):
                check_scope(self.rules, branch, paths)

    def test_rename_checks_original_and_new_path(self):
        pr = {"head":{"sha":"abc","ref":"work/delivery"},"base":{"sha":"123"},"number":7,"changed_files":1}
        moved = [{"filename":"frontend/src/features/delivery/Attempt.jsx","previous_filename":"frontend/src/design/Folio.jsx"}]
        with tempfile.TemporaryDirectory() as tmp:
            event = Path(tmp) / "event.json"
            event.write_text(json.dumps({"pull_request":pr}))
            env = {"GITHUB_EVENT_PATH":str(event),"GITHUB_API_URL":"https://api.example.test",
                   "GITHUB_REPOSITORY":"org/exam","GITHUB_TOKEN":"mock"}
            with patch.dict(os.environ,env), patch("check_scope.urlopen") as fetch:
                fetch.return_value.__enter__.return_value.read.side_effect=[json.dumps(pr),json.dumps(moved),json.dumps(pr)]
                branch, paths=read_pr()
                with self.assertRaises(ValueError):
                    check_scope(self.rules,branch,paths)

    def test_each_srs_requirement_assigned_once(self):
        import re
        ids=[r for lane in self.rules.values() for r in lane["requirements"]]
        expected=set(re.findall(r"^(?:FR|SR|IN|NFR|DEL)\d{2}\b",(ROOT / "docs/requirements.md").read_text(),re.M))
        self.assertEqual(len(ids),len(set(ids)))
        self.assertEqual(set(ids),expected)
        self.assertEqual(len(expected),29)

if __name__ == "__main__":
    unittest.main()
