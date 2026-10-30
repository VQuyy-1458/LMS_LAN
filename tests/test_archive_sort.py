import csv
import io
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app import submission_archive as archive


class ArchiveOrderTests(unittest.TestCase):
    def records(self):
        start=datetime(2026,10,29,tzinfo=timezone.utc)
        return [{"id":str(i),"course_id":"course","student_id":f"SV{i}","full_name":f"Student {i}","kind":"assignment","activity_id":"assignment:task","title":"Task","filename":f"answer{i}.txt","course_name":"Course","submitted_at":(start+timedelta(minutes=i)).isoformat(),"attempt":i+1,"available":True,"score":None,"max_score":10,"selected":False,"sha256":"","status":"pending"} for i in range(25)]

    def test_time_order_is_applied_before_pagination(self):
        rows=list(reversed(self.records()))
        with patch.object(archive,"_index",return_value=rows):
            ascending=archive.listing({"page":"2"})
            descending=archive.listing({"page":"2","order":"desc"})
        self.assertEqual([r["id"] for r in ascending["rows"]],[str(i) for i in range(10,20)])
        self.assertEqual([r["id"] for r in descending["rows"]],[str(i) for i in range(14,4,-1)])
        self.assertEqual(ascending["total"],25)

    def test_basis_is_fixed_and_csv_uses_the_same_time_order(self):
        rows=list(reversed(self.records()))
        with patch.object(archive,"_index",return_value=rows):
            expected=archive.listing({"sort":"student_id","order":"asc"})["rows"]
            exported=list(csv.reader(io.StringIO(archive.export_csv({"order":"asc"}).decode("utf-8-sig"))))
        self.assertEqual([r["id"] for r in expected],[str(i) for i in range(10)])
        self.assertEqual([r[0] for r in exported[1:]],[str(i) for i in range(25)])

    def test_group_representative_stays_latest_in_either_direction(self):
        rows=self.records()[:2]
        for row in rows: row["student_id"]="SV1"
        with patch.object(archive,"_index",return_value=rows):
            for order in ("asc","desc"):
                result=archive.listing({"mode":"group","order":order})
                self.assertEqual(result["rows"][0]["id"],"1")
                self.assertEqual(result["rows"][0]["attempt_count"],2)


if __name__=="__main__":
    unittest.main()
