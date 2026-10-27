from datetime import date
import streamlit as st, pandas as pd
from werkzeug.security import generate_password_hash, check_password_hash
import core
import ui
from core import q, ex, YEARS, DAYS, POSES, plan_text

st.set_page_config(page_title="Smart Attendance", page_icon="🎓", layout="wide")
ui.inject()
ui.enter_nav()
S = st.session_state

def opts(k): return [r["name"] for r in q("SELECT name FROM options WHERE kind=? ORDER BY name", (k,))]
def save_img(b, side=1280): return core.save_image(b, side)
def img(n): return core.get_image(n)
def class_picker(key):
    c = st.columns(4)
    v = (c[0].selectbox("Department", opts("dept"), key=key + "d"), c[1].selectbox("Year", YEARS, key=key + "y"),
         c[2].selectbox("Section", opts("section"), key=key + "s"), c[3].selectbox("Academic year", opts("acad"), key=key + "a"))
    if not all(v): st.info("The admin must add departments, sections and academic years first.")
    return v if all(v) else None
def fresh(): return S.get("fresh", 0)
def storage_warning():
    if not core.using_postgres() and core.BASE.startswith("/mount/src"):
        st.warning("Temporary storage: this deployment is not connected to a database, so all accounts are erased whenever the app restarts "
                   "(the admin sign-up then appears again). Add DATABASE_URL under Settings, then Secrets.")
def done(msg):   # success: show a message and give the form a brand-new blank copy
    S.fresh = fresh() + 1; S.flash = msg; st.rerun()
def add_user(username, pw, role, name, status="active"):
    return ex("INSERT INTO users(username,password_hash,role,name,status) VALUES(?,?,?,?,?)",
              (username.strip(), generate_password_hash(pw), role, name, status)).lastrowid

# ---------------- login and sign up ----------------
def login_page():
    first = not q("SELECT 1 FROM users WHERE role='admin'", one=True)
    ui.hero("Smart Attendance", "Face-recognition attendance for students, faculty and administrators.",
            ["Photo-based attendance", "Live percentage and risk alerts", "Timetable aware"])
    _, mid, _ = st.columns([1, 1.7, 1])
    with mid:
        if S.get("flash"): st.success(S.pop("flash"))
        storage_warning()
        need = core.get_secret("ADMIN_SETUP_CODE")
        if first:
            ui.section("Admin sign up", "No admin exists yet. Create the administrator account to begin.")
            with st.form(f"setup{fresh()}"):
                n, u = st.text_input("Full name"), st.text_input("Admin ID")
                p, p2 = st.text_input("Password (min 6 characters)", type="password"), st.text_input("Confirm password", type="password")
                code = st.text_input("Setup code", type="password") if need else ""
                if st.form_submit_button("Create admin account", **ui.wide(st.form_submit_button)):
                    ok = False
                    if not (n.strip() and u.strip()): st.error("Fill the name and the admin ID.")
                    elif len(p) < 6: st.error("The password needs at least 6 characters.")
                    elif p != p2: st.error("The two passwords do not match.")
                    elif need and code != need: st.error("Wrong setup code.")
                    else: add_user(u, p, "admin", n); ok = True
                    if ok: done("Admin account created. You can now log in.")
            return
        allow_up = (q("SELECT value FROM settings WHERE key='faculty_signup'", one=True) or {"value": "0"})["value"] == "1"
        tab_in, tab_up = st.tabs(["🔐 Log in", "✨ Sign up"]) if allow_up else (st.container(), None)
        with tab_in:
            for tab, role in zip(st.tabs(["🎓 Student login", "🧑‍🏫 Faculty login", "🛡️ Admin login"]), ("student", "faculty", "admin")):
                with tab, st.form("login_" + role):
                    u, p = st.text_input("ID", key=f"u_{role}"), st.text_input("Password", type="password", key=f"p_{role}")
                    if st.form_submit_button(f"Sign in as {role}", **ui.wide(st.form_submit_button)):
                        r = q("SELECT * FROM users WHERE username=?", (u.strip(),), one=True)
                        if not (r and r["role"] == role and check_password_hash(r["password_hash"], p)): st.error("Wrong ID, password, or login type.")
                        elif (r["status"] or "active") != "active": st.warning("Your account is waiting for the admin's approval.")
                        else: S.user = dict(id=r["id"], role=role, name=r["name"]); st.rerun()
        if tab_up is None: return   # sign-up is switched off: only the logins show
        with tab_up:
            ui.section("Faculty sign up", "The admin must approve your account before you can log in.")
            with st.form(f"fsign{fresh()}"):
                n, u = st.text_input("Full name", key=f"fs_n{fresh()}"), st.text_input("Faculty ID", key=f"fs_u{fresh()}")
                p = st.text_input("Password (min 6 characters)", type="password", key=f"fs_p{fresh()}")
                if st.form_submit_button("Request faculty account", **ui.wide(st.form_submit_button)):
                    ok = False
                    if not (n.strip() and u.strip()): st.error("Fill the name and the ID.")
                    elif len(p) < 6: st.error("The password needs at least 6 characters.")
                    else:
                        try: add_user(u, p, "faculty", n, "pending"); ok = True
                        except Exception: st.error("That ID is already taken.")
                    if ok: done("Request sent. You can log in after the admin approves it.")
            st.caption("Students do not sign up. Your faculty creates your login and gives you the ID and password.")

# ---------------- admin ----------------
def admin_faculty():
    ui.section("Faculty")
    pend = q("SELECT * FROM users WHERE role='faculty' AND status='pending' ORDER BY name")
    if pend:
        ui.callout(f"<b>{len(pend)}</b> faculty sign-up request(s) waiting for approval.", "warn")
        for f in pend:
            c = st.columns([3, 3, 1, 1]); c[0].write(f["name"]); c[1].write(f["username"])
            if c[2].button("Approve", key=f"ap{f['id']}"): ex("UPDATE users SET status='active' WHERE id=?", (f["id"],)); st.rerun()
            if c[3].button("Reject", key=f"rj{f['id']}"): ex("DELETE FROM users WHERE id=?", (f["id"],)); st.rerun()
    with st.form(f"addf{fresh()}"):
        c = st.columns(3); n, u, p = c[0].text_input("Name"), c[1].text_input("Faculty ID"), c[2].text_input("Password", type="password")
        if st.form_submit_button("Add faculty"):
            ok = False
            if not (n.strip() and u.strip() and p): st.error("Fill the name, ID and password.")
            else:
                try: add_user(u, p, "faculty", n); ok = True
                except Exception: st.error("That ID already exists.")
            if ok: done("Faculty added.")
    for f in q("SELECT * FROM users WHERE role='faculty' AND (status IS NULL OR status='active') ORDER BY name"):
        c = st.columns([3, 3, 1]); c[0].write(f["name"]); c[1].write(f["username"])
        if c[2].button("Remove", key=f"df{f['id']}"): ex("DELETE FROM users WHERE id=?", (f["id"],)); st.rerun()

def admin_setup():
    ui.section("Departments, sections, academic years, subjects")
    cols = st.columns(3)
    for col, (kind, label) in zip(cols, (("dept", "Departments"), ("section", "Sections"), ("acad", "Academic years"))):
        with col:
            st.subheader(label)
            with st.form(f"o{kind}{fresh()}"):
                v = st.text_input("Add", key=f"add_{kind}{fresh()}", placeholder="2025-26" if kind == "acad" else "A" if kind == "section" else "AI&DS")
                if st.form_submit_button("Add"):
                    ok = False
                    if not v.strip(): st.error("Type a name first.")
                    else:
                        try: ex("INSERT INTO options(kind,name) VALUES(?,?)", (kind, v.strip())); ok = True
                        except Exception: st.error("Already exists.")
                    if ok: done(f"{label[:-1] if label.endswith('s') else label} added.")
            for o in q("SELECT * FROM options WHERE kind=? ORDER BY name", (kind,)):
                a, b = st.columns([4, 1]); a.write(o["name"])
                if b.button("✕", key=f"o{o['id']}"): ex("DELETE FROM options WHERE id=?", (o["id"],)); st.rerun()
    st.subheader("Subjects")
    with st.form(f"subj{fresh()}"):
        c = st.columns(3); n = c[0].text_input("Subject name"); d = c[1].selectbox("Department", opts("dept")); y = c[2].selectbox("Year", YEARS)
        if st.form_submit_button("Add subject"):
            ok = False
            if not (n.strip() and d): st.error("Type the subject name and choose a department.")
            else:
                try: ex("INSERT INTO subjects(name,dept,year) VALUES(?,?,?)", (n.strip(), d, y)); ok = True
                except Exception: st.error("Subject already exists for that department and year.")
            if ok: done("Subject added.")
    for s in q("SELECT * FROM subjects ORDER BY dept,year,name"):
        c = st.columns([4, 2, 1, 1]); c[0].write(s["name"]); c[1].write(s["dept"]); c[2].write(f"Year {s['year']}")
        if c[3].button("Remove", key=f"s{s['id']}"): ex("DELETE FROM subjects WHERE id=?", (s["id"],)); st.rerun()

def admin_rules():
    ui.section("Attendance rules (%) and admin login"); t = core.thresholds()
    with st.form("rules"):
        c = st.columns(3); s = c[0].number_input("Safe at or above", 1, 100, t["safe"]); f = c[1].number_input("Fine below", 1, 100, t["fine"])
        d = c[2].number_input("Debar below", 1, 100, t["debar"])
        if st.form_submit_button("Save rules"):
            if s > f > d:
                for k, v in (("safe", s), ("fine", f), ("debar", d)): ex("UPDATE settings SET value=? WHERE key=?", (str(v), k))
                st.success("Saved.")
            else: st.error("Thresholds must satisfy safe > fine > debar.")
    allow = (q("SELECT value FROM settings WHERE key='faculty_signup'", one=True) or {"value": "0"})["value"] == "1"
    with st.form("fsu"):
        on = st.checkbox("Show a faculty Sign up tab on the login page (you approve every request)", value=allow)
        if st.form_submit_button("Save sign-up setting"): ex("UPDATE settings SET value=? WHERE key='faculty_signup'", ("1" if on else "0",)); st.success("Saved.")
    with st.form("acct"):
        u, p = st.text_input("New admin ID"), st.text_input("New password", type="password")
        if st.form_submit_button("Update my login") and u and p:
            try: ex("UPDATE users SET username=?, password_hash=? WHERE id=?", (u.strip(), generate_password_hash(p), S.user["id"])); st.success("Updated.")
            except Exception: st.error("That ID is taken.")

# ---------------- timetable ----------------
def timetable_page():
    ui.section("Timetable")
    if S.user["role"] == "student":
        s = q("SELECT * FROM students WHERE user_id=?", (S.user["id"],), one=True)
        if not s: st.error("Your student record was not found."); return
        c = (s["dept"], s["year"], s["section"], s["acad"])
    else: c = class_picker("tt")
    if not c: return
    cells = {(r["day"], r["period"]): r["subject"] for r in q("SELECT * FROM timetable WHERE dept=? AND year=? AND section=? AND acad=?", c)}
    if S.user["role"] != "admin":
        st.table(pd.DataFrame([[cells.get((d, p), "") for p in range(1, 9)] for d in range(6)], index=DAYS, columns=[f"P{p}" for p in range(1, 9)])); return
    subs = [""] + [r["name"] for r in q("SELECT name FROM subjects WHERE dept=? AND year=? ORDER BY name", (c[0], c[1]))]
    if len(subs) == 1: st.warning("Add subjects for this department and year first.")
    with st.form("ttf"):
        hdr = st.columns(9); vals = {}
        for p in range(1, 9): hdr[p].markdown(f"**P{p}**")
        for d in range(6):
            row = st.columns(9); row[0].markdown(f"**{DAYS[d]}**")
            for p in range(1, 9):
                cur = cells.get((d, p), ""); vals[(d, p)] = row[p].selectbox(f"{DAYS[d]}{p}", subs, index=subs.index(cur) if cur in subs else 0,
                                                                           key=f"t{'|'.join(c)}{d}{p}", label_visibility="collapsed")
        if st.form_submit_button("Save timetable"):
            ex("DELETE FROM timetable WHERE dept=? AND year=? AND section=? AND acad=?", c)
            for (d, p), v in vals.items():
                if v: ex("INSERT INTO timetable(dept,year,section,acad,day,period,subject) VALUES(?,?,?,?,?,?,?)", (*c, d, p, v))
            st.success("Timetable saved.")

# ---------------- faculty: students ----------------
def remove_student(sid):
    s = q("SELECT * FROM students WHERE id=?", (sid,), one=True)
    core.delete_images([r["filename"] for r in q("SELECT filename FROM student_photos WHERE student_id=?", (sid,))] + [s["photo"] or ""])
    ex("DELETE FROM users WHERE id=?", (s["user_id"],))

def add_student_form(dept, year):
    default = st.radio("Add photos by", ["Upload photo", "Take photo"], horizontal=True, key="photo_default")
    st.caption("Profile picture and front view are required. Far view about 3-4 m away, near view as a close-up.")
    def grab(label, key):
        choices = ["Upload photo", "Take photo"]
        how = st.radio("Photo source", choices, index=choices.index(default), horizontal=True, key=f"how_{key}_{default}", label_visibility="collapsed")
        if how == "Take photo": return st.camera_input(label, key=f"{key}_cam")
        return st.file_uploader(label, type=["jpg", "jpeg", "png"], key=f"{key}_up")
    c = st.columns(4); name, roll = c[0].text_input("Name"), c[1].text_input("Roll no (login ID)"); pw = c[2].text_input("Login password")
    sec = c[3].selectbox("Section", opts("section")); acad = st.selectbox("Academic year", opts("acad"))
    st.markdown("**Photos**"); files = {}
    with st.expander("Profile picture (required)", expanded=True): files["profile"] = grab("Profile picture", "ph_profile")
    for k, label in POSES:
        with st.expander(label + (" (required)" if k == "front" else "")): files[k] = grab(label, "ph_" + k)
    if st.button("Save student", type="primary"):
        if not (name and roll and pw and sec and acad and files["profile"] and files["front"]): st.error("Fill every field and add the profile and front photos."); return
        try: uid = add_user(roll, pw, "student", name)
        except Exception: st.error("That roll number / ID already exists."); return
        sid = ex("INSERT INTO students(user_id,roll_no,name,dept,year,section,acad,photo) VALUES(?,?,?,?,?,?,?,?)",
                 (uid, roll.strip(), name, dept, year, sec, acad, save_img(files["profile"].getvalue(), 500))).lastrowid
        skipped = []
        for k, label in POSES:
            if files[k]:
                data = files[k].getvalue(); enc = core.encode_photo(data)
                if enc: ex("INSERT INTO student_photos(student_id,pose,filename,encoding) VALUES(?,?,?,?)", (sid, k, save_img(data), enc))
                else: skipped.append(label)
        if not q("SELECT 1 FROM student_photos WHERE student_id=? AND pose='front'", (sid,), one=True):
            remove_student(sid); st.error("No face found in the front photo. Retake it with the face clearly visible."); return
        S.adding = False; S.flash = "Student added." + (f" No face found in: {', '.join(skipped)} (not saved)." if skipped else ""); st.rerun()

def students_page():
    ui.section("Students")
    if S.get("flash"): st.success(S.pop("flash"))
    if not S.get("dept"):
        cols = st.columns(3)
        for i, d in enumerate(opts("dept")):
            n = q("SELECT COUNT(*) c FROM students WHERE dept=?", (d,), one=True)["c"]
            with cols[i % 3]:
                ui.tile(d, f"{n} student{'' if n == 1 else 's'}", "🏛️")
                if st.button("Open department", key="d" + d, **ui.wide(st.button)): S.dept = d; st.rerun()
        if not opts("dept"): st.info("The admin must add departments first.")
        return
    if not S.get("year"):
        if st.button("← Departments"): S.dept = None; st.rerun()
        ui.section(S.dept, "Choose a year")
        cols = st.columns(4)
        for i, y in enumerate(YEARS):
            n = q("SELECT COUNT(*) c FROM students WHERE dept=? AND year=?", (S.dept, y), one=True)["c"]
            with cols[i]:
                ui.tile(f"Year {y}", f"{n} student{'' if n == 1 else 's'}", "📚")
                if st.button("Open year", key="y" + y, **ui.wide(st.button)): S.year = y; st.rerun()
        return
    if st.button(f"← {S.dept} years"): S.year = None; S.adding = False; st.rerun()
    ui.section(f"{S.dept} · Year {S.year}", "Students, photos and logins")
    if S.get("adding"):
        if st.button("Cancel"): S.adding = False; st.rerun()
        return add_student_form(S.dept, S.year)
    if st.button("➕ Add student"): S.adding = True; st.rerun()
    sec = st.selectbox("Section", ["All"] + opts("section"))
    for s in q("""SELECT s.*, (SELECT COUNT(*) FROM student_photos p WHERE p.student_id=s.id) n FROM students s
                  WHERE dept=? AND year=? AND (?='All' OR section=?) ORDER BY section,roll_no""", (S.dept, S.year, sec, sec)):
        c = st.columns([1, 2, 3, 1, 2, 2, 1])
        pic = img(s["photo"])
        if pic: c[0].image(pic, width=50)
        c[1].write(s["roll_no"]); c[2].write(s["name"]); c[3].write(s["section"]); c[4].write(s["acad"]); c[5].write(f"{s['n']} face photos")
        if c[6].button("Remove", key=f"rs{s['id']}"): remove_student(s["id"]); st.rerun()
        with st.expander(f"Reset password · {s['name']}"):
            np_ = st.text_input("New password", key=f"pw{s['id']}")
            if st.button("Set", key=f"sp{s['id']}") and np_:
                ex("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(np_), s["user_id"])); st.success("Password reset.")

# ---------------- faculty: attendance ----------------
def attendance_page():
    ui.section("Take attendance from a classroom photo")
    if S.get("saved"): st.success(S.pop("saved"))
    c = class_picker("at")
    if not c: return
    r = st.columns(3); day = r[0].date_input("Date", date.today()); period = r[1].selectbox("Period", range(1, 9))
    subs = [x["name"] for x in q("SELECT name FROM subjects WHERE dept=? AND year=? ORDER BY name", (c[0], c[1]))]
    tt = q("SELECT subject FROM timetable WHERE dept=? AND year=? AND section=? AND acad=? AND day=? AND period=?", (*c, day.weekday(), period), one=True)
    subject = r[2].selectbox("Subject", subs, index=subs.index(tt["subject"]) if tt and tt["subject"] in subs else 0)
    how = st.radio("Add the classroom photo by", ["Upload photo", "Take photo", "Both"], horizontal=True)
    photos = []
    if how in ("Upload photo", "Both"): photos += st.file_uploader("Upload classroom photo(s)", type=["jpg", "jpeg", "png"], accept_multiple_files=True, key="cls_up")
    if how in ("Take photo", "Both"):
        shot = st.camera_input("Take a classroom photo", key="cls_cam")
        if shot: photos.append(shot)
    st.caption("Webcams give low-resolution photos. In a big room, upload a high-resolution photo taken with a phone so far-away faces are found.")
    if st.button("Identify students", type="primary"):
        cls = q("SELECT * FROM students WHERE dept=? AND year=? AND section=? AND acad=? ORDER BY roll_no", c)
        if not (cls and photos and subject): st.error("Need students in this class, a subject and at least one photo."); return
        known = {s["id"]: [x["encoding"] for x in q("SELECT encoding FROM student_photos WHERE student_id=?", (s["id"],))] for s in cls}
        with st.spinner("Scanning faces..."): present, faces = core.recognize([p.getvalue() for p in photos], {k: v for k, v in known.items() if v})
        for s in cls: S[f"pr{s['id']}"] = s["id"] in present
        S.review = dict(ids=[s["id"] for s in cls], faces=faces, meta=(subject, str(day), period))
    rv = S.get("review")
    if rv:
        st.subheader("Review"); st.write(f"{rv['faces']} face(s) detected. Correct anything the camera missed, then save.")
        for s in q(f"SELECT * FROM students WHERE id IN ({','.join('?' * len(rv['ids']))}) ORDER BY roll_no", rv["ids"]):
            a, b = st.columns([1, 8])
            pic = img(s["photo"])
            if pic: a.image(pic, width=45)
            b.checkbox(f"{s['roll_no']} · {s['name']}", key=f"pr{s['id']}")
        if st.button("Save attendance", type="primary"):
            sub, d, p = rv["meta"]; n = 0
            for sid in rv["ids"]:
                pr = S[f"pr{sid}"]; n += pr
                ex("""INSERT INTO attendance(student_id,subject,date,period,status,marked_by) VALUES(?,?,?,?,?,?)
                      ON CONFLICT(student_id,subject,date,period) DO UPDATE SET status=excluded.status, marked_by=excluded.marked_by""",
                   (sid, sub, d, p, "Present" if pr else "Absent", S.user["id"]))
            S.review = None; S.saved = f"Attendance saved: {n} present."; st.rerun()

def analysis_page():
    ui.section("Attendance analysis"); t = core.thresholds()
    rows = q("""SELECT s.roll_no,s.name,s.dept,s.year,a.subject,SUM(CASE WHEN a.status='Present' THEN 1 ELSE 0 END) p,COUNT(*) n FROM students s
                JOIN attendance a ON a.student_id=s.id GROUP BY s.id,a.subject ORDER BY s.dept,s.year,s.roll_no""")
    out = [{"Roll no": r["roll_no"], "Name": r["name"], "Dept": r["dept"], "Year": r["year"], "Subject": r["subject"],
            "Attended": f"{int(r['p'])}/{r['n']}", "%": core.summarize(int(r["p"]), int(r["n"]), t)["pct"], "Status": core.summarize(int(r["p"]), int(r["n"]), t)["status"]} for r in rows]
    if out: st.dataframe(pd.DataFrame(out), **ui.wide(st.dataframe))
    else: st.info("No attendance recorded yet.")

# ---------------- student ----------------
def student_page():
    s = q("SELECT * FROM students WHERE user_id=?", (S.user["id"],), one=True)
    if not s: st.error("Your student record was not found. Ask your faculty."); return
    r = core.student_report(s["id"]); t, o = r["t"], r["overall"]
    a, b = st.columns([1, 7])
    pic = img(s["photo"])
    if pic: a.image(pic, width=96)
    with b: ui.section(s["name"], f"{s['roll_no']} · {s['dept']} · Year {s['year']}-{s['section']} · {s['acad']}")
    c = st.columns([1.2, 1, 1, 1])
    with c[0]: ui.ring(o["pct"], o["status"])
    with c[1]: ui.stat("Status", ui.chip(o["status"]))
    with c[2]: ui.stat("Periods attended", f"{o['present']}/{o['total']}")
    with c[3]: ui.stat("Fine / Debar below", f"{t['fine']}% / {t['debar']}%")
    ui.callout(f"<b>To avoid a fine</b> ({t['fine']}%): {plan_text(o['avoid_fine'])}.<br><b>To avoid debarment</b> ({t['debar']}%): {plan_text(o['avoid_debar'])}.",
               "ok" if o["status"] == "Safe" else "warn")
    if not r["subjects"]: st.info("No attendance recorded yet."); return
    ui.section("Subject-wise attendance", "Periods you need to attend, or can still skip, per subject")
    items = list(r["subjects"].items()); cols = st.columns(2)
    for i, (n, x) in enumerate(items):
        with cols[i % 2]: ui.subject_card(n, x, t)
    ui.section("Graphs"); g = st.columns(2)
    g[0].bar_chart(pd.Series({n: x["pct"] for n, x in items}, name="Subject %"), color="#6d28d9")
    g[1].line_chart(pd.Series({m: x["pct"] for m, x in r["months"].items()}, name="Monthly %"), color="#4f46e5")
    ui.section("Month-wise and history")
    st.dataframe(pd.DataFrame([{"Month": m, "Attended": f"{x['present']}/{x['total']}", "%": x["pct"]} for m, x in r["months"].items()]), **ui.wide(st.dataframe), hide_index=True)
    st.dataframe(pd.DataFrame([dict(h) for h in r["history"]]), **ui.wide(st.dataframe), hide_index=True)

# ---------------- router ----------------
try: core.q("SELECT 1")
except Exception as e:
    st.error("Could not connect to the database. Check DATABASE_URL in the app's Secrets."); st.code(str(e)); st.stop()
if S.get("user") and not q("SELECT 1 FROM users WHERE id=?", (S.user["id"],), one=True): S.user = None
if not S.get("user"): login_page(); st.stop()
role = S.user["role"]
pages = {"admin": {"Faculty": admin_faculty, "Subjects & options": admin_setup, "Timetable": timetable_page, "Rules & account": admin_rules, "Analysis": analysis_page},
         "faculty": {"Students": students_page, "Take attendance": attendance_page, "Timetable": timetable_page, "Analysis": analysis_page},
         "student": {"My attendance": student_page, "Timetable": timetable_page}}[role]
ui.brand(S.user["name"], role); choice = st.sidebar.radio("Menu", list(pages), label_visibility="collapsed")
st.sidebar.caption("Version 3.3")
if st.sidebar.button("Sign out"): S.clear(); st.rerun()
if S.get("flash"): st.success(S.pop("flash"))
if role == "admin": storage_warning()
pages[choice]()
