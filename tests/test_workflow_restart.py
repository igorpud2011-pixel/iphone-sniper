import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def scanner_script():
    lines=(ROOT/'.github/workflows/monitor.yml').read_text().splitlines()
    start=next(i for i,line in enumerate(lines) if line.strip()=='if [ "$TEST_DISCORD" = "true" ]; then')
    block=[]
    for line in lines[start:]:
        if line.strip() and not line.startswith('          '):break
        block.append(line[10:])
    return '\n'.join(block)

class WorkflowRestartTests(unittest.TestCase):
    def test_new_code_restarts_before_second_scan_and_last_failure_is_visible(self):
        for scan_code in (0,2):
            with self.subTest(scan_code=scan_code),tempfile.TemporaryDirectory() as tmp:
                folder=Path(tmp)
                fake_git=folder/'git'
                fake_git.write_text('''#!/bin/bash
if [ "$1" = diff ] && [ "$2" = --quiet ]; then
  if [ -e "$TEST_ROOT/pulled" ]; then exit 0; else exit 1; fi
fi
if [ "$1" = diff ] && [ "$2" = --cached ]; then exit 1; fi
if [ "$1" = pull ]; then touch "$TEST_ROOT/pulled"; fi
exit 0
''')
                fake_python=folder/'python'
                fake_python.write_text('#!/bin/bash\necho scan >> "$TEST_ROOT/scans"\nexit "$TEST_SCAN_CODE"\n')
                fake_git.chmod(0o755);fake_python.chmod(0o755)
                env={**os.environ,'PATH':str(folder)+os.pathsep+os.environ['PATH'],'TEST_ROOT':tmp,'TEST_SCAN_CODE':str(scan_code),'TEST_DISCORD':'false','SESSION_MINUTES':'1'}
                result=subprocess.run(['bash','-e'],input=scanner_script(),text=True,env=env,cwd=tmp,capture_output=True,timeout=4)
                self.assertEqual(result.returncode,scan_code,result.stderr)
                self.assertEqual((folder/'scans').read_text().splitlines(),['scan'])
                self.assertTrue((folder/'pulled').exists())
