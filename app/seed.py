"""Synthetic reference data only - no real people or facilities."""
USERS = [("u-admin", "Admin", "admin"), ("u-fm", "Facility Manager", "facility_manager"),
         ("u-tech", "Technician", "maintenance_technician"), ("u-appr", "Dept Approver", "department_approver"),
         ("u-fac", "Faculty Member", "faculty"), ("u-stu", "Student A", "student"),
         ("u-stu2", "Student B", "student"), ("sensor-gw", "Sensor Gateway", "sensor")]
FACILITIES = [("Classroom A101", "classroom", 0), ("Seminar Hall", "hall", 0),
              ("Chemistry Lab", "lab", 1), ("Meeting Room M2", "meeting_room", 0)]


def seed(conn):
    conn.executemany("INSERT OR IGNORE INTO users VALUES (?,?,?)", USERS)
    if not conn.execute("SELECT 1 FROM facilities").fetchone():
        conn.executemany("INSERT INTO facilities(name,kind,restricted) VALUES (?,?,?)", FACILITIES)
    conn.commit()
