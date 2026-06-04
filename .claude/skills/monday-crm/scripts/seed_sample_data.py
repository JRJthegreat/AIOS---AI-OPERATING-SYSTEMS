#!/usr/bin/env python3
"""
Law Firm CRM — Seed Dummy Data (v2)

Fully populates all boards with realistic dummy data.
Fetches column IDs dynamically so it works after any setup run.

Run AFTER setup_crm.py:
    cd ".claude/skills/monday-crm/scripts"
    python3 seed_sample_data.py
"""

import sys
import json
from pathlib import Path
from datetime import date, timedelta

sys.path.insert(0, str(Path(__file__).parent))
import monday_client as mc

CONFIG_PATH = Path(__file__).parent.parent / "config.json"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print("ERROR: config.json not found. Run setup_crm.py first.")
        sys.exit(1)
    return json.loads(CONFIG_PATH.read_text())


def d(offset_days: int) -> str:
    return (date.today() + timedelta(days=offset_days)).isoformat()


def col_map(board_id: int) -> dict:
    """Return {column_title: column_id} for a board."""
    cols = mc.get_columns(board_id)
    return {c["title"]: c["id"] for c in cols}


# ── Intake / Leads ────────────────────────────────────────────────────────────

def seed_intake(board_id: int, groups: dict):
    print("\n  Seeding: Intake / Leads")
    cm = col_map(board_id)

    STATUS_GROUP = {
        "New":               "New",
        "Consult Scheduled": "In Progress",
        "Retainer Signed":   "In Progress",
        "Lost":              "Closed",
    }

    items = [
        ("Maria Gonzalez", "New", {
            cm["Status"]:            {"label": "New"},
            cm["Inquiry Type"]:      {"labels": ["Immigration"]},
            cm["Source"]:            {"labels": ["Website"]},
            cm["Phone"]:             {"phone": "+13055550192", "countryShortName": "US"},
            cm["Email"]:             {"email": "maria.gonzalez@email.com", "text": "maria.gonzalez@email.com"},
            cm["Consultation Date"]: {"date": d(3)},
            cm["Notes"]:             {"text": "Seeking asylum after political persecution. Has UNHCR documentation. Speaks Spanish and English."},
        }),
        ("James Carter", "Retainer Signed", {
            cm["Status"]:            {"label": "Retainer Signed"},
            cm["Inquiry Type"]:      {"labels": ["Criminal Defense"]},
            cm["Source"]:            {"labels": ["Referral"]},
            cm["Phone"]:             {"phone": "+14045550147", "countryShortName": "US"},
            cm["Email"]:             {"email": "james.carter@gmail.com", "text": "james.carter@gmail.com"},
            cm["Consultation Date"]: {"date": d(-5)},
            cm["Notes"]:             {"text": "DUI charge, BAC 0.12. Prior clean record. Referred by attorney Marcus Webb. Retainer paid in full."},
        }),
        ("Priya Patel", "New", {
            cm["Status"]:            {"label": "New"},
            cm["Inquiry Type"]:      {"labels": ["Immigration"]},
            cm["Source"]:            {"labels": ["Social Media"]},
            cm["Phone"]:             {"phone": "+12125550183", "countryShortName": "US"},
            cm["Email"]:             {"email": "priya.patel@email.com", "text": "priya.patel@email.com"},
            cm["Consultation Date"]: {"date": d(7)},
            cm["Notes"]:             {"text": "H1B visa appeal after employer filed incorrectly. Currently on OPT extension. Deadline critical."},
        }),
        ("David Thompson", "Lost", {
            cm["Status"]:            {"label": "Lost"},
            cm["Inquiry Type"]:      {"labels": ["Criminal Defense"]},
            cm["Source"]:            {"labels": ["Website"]},
            cm["Phone"]:             {"phone": "+17135550261", "countryShortName": "US"},
            cm["Email"]:             {"email": "d.thompson@email.com", "text": "d.thompson@email.com"},
            cm["Consultation Date"]: {"date": d(-14)},
            cm["Notes"]:             {"text": "Assault charge. Chose to go with public defender after consultation. Follow up in 30 days."},
        }),
        ("Sofia Ramirez", "Consult Scheduled", {
            cm["Status"]:            {"label": "Consult Scheduled"},
            cm["Inquiry Type"]:      {"labels": ["Family"]},
            cm["Source"]:            {"labels": ["Referral"]},
            cm["Phone"]:             {"phone": "+17865550374", "countryShortName": "US"},
            cm["Email"]:             {"email": "sofia.ramirez@email.com", "text": "sofia.ramirez@email.com"},
            cm["Consultation Date"]: {"date": d(2)},
            cm["Notes"]:             {"text": "Child custody dispute following divorce. Wants sole custody. Two children ages 6 and 9. Referred by Elena Vasquez."},
        }),
        ("Kevin Wu", "Retainer Signed", {
            cm["Status"]:            {"label": "Retainer Signed"},
            cm["Inquiry Type"]:      {"labels": ["Criminal Defense"]},
            cm["Source"]:            {"labels": ["Walk-in"]},
            cm["Phone"]:             {"phone": "+16175550428", "countryShortName": "US"},
            cm["Email"]:             {"email": "kevin.wu@email.com", "text": "kevin.wu@email.com"},
            cm["Consultation Date"]: {"date": d(-8)},
            cm["Notes"]:             {"text": "Drug possession (marijuana). First offense. Requesting diversion program. Retainer $3,500 paid."},
        }),
        ("Antoine Bernard", "Consult Scheduled", {
            cm["Status"]:            {"label": "Consult Scheduled"},
            cm["Inquiry Type"]:      {"labels": ["Immigration"]},
            cm["Source"]:            {"labels": ["Referral"]},
            cm["Phone"]:             {"phone": "+13055550531", "countryShortName": "US"},
            cm["Email"]:             {"email": "a.bernard@email.com", "text": "a.bernard@email.com"},
            cm["Consultation Date"]: {"date": d(5)},
            cm["Notes"]:             {"text": "Deportation order received. TPS application pending. Haitian national, has US-born children. Urgent."},
        }),
        ("Lisa Hernandez", "New", {
            cm["Status"]:            {"label": "New"},
            cm["Inquiry Type"]:      {"labels": ["Criminal Defense"]},
            cm["Source"]:            {"labels": ["Website"]},
            cm["Phone"]:             {"phone": "+19545550619", "countryShortName": "US"},
            cm["Email"]:             {"email": "lisa.hernandez@email.com", "text": "lisa.hernandez@email.com"},
            cm["Consultation Date"]: {"date": d(4)},
            cm["Notes"]:             {"text": "DUI charge, first offense. BAC 0.09. Contested breathalyzer results. Wants to avoid license suspension."},
        }),
        ("Michael O'Brien", "Retainer Signed", {
            cm["Status"]:            {"label": "Retainer Signed"},
            cm["Inquiry Type"]:      {"labels": ["Family"]},
            cm["Source"]:            {"labels": ["Referral"]},
            cm["Phone"]:             {"phone": "+16175550743", "countryShortName": "US"},
            cm["Email"]:             {"email": "m.obrien@email.com", "text": "m.obrien@email.com"},
            cm["Consultation Date"]: {"date": d(-10)},
            cm["Notes"]:             {"text": "High-asset divorce. Jointly owned business valued at $2.3M. Seeking equitable distribution. Referred by attorney."},
        }),
        ("Yemi Adeyemi", "New", {
            cm["Status"]:            {"label": "New"},
            cm["Inquiry Type"]:      {"labels": ["Immigration"]},
            cm["Source"]:            {"labels": ["Social Media"]},
            cm["Phone"]:             {"phone": "+12405550856", "countryShortName": "US"},
            cm["Email"]:             {"email": "y.adeyemi@email.com", "text": "y.adeyemi@email.com"},
            cm["Consultation Date"]: {"date": d(8)},
            cm["Notes"]:             {"text": "Political asylum from Nigeria. Journalist who received death threats. Strong documentation available."},
        }),
    ]

    for name, status, cols in items:
        group_id = groups[STATUS_GROUP[status]]
        item = mc.create_item(board_id, group_id, name, cols)
        print(f"    + {name} ({status}) — id={item.get('id')}")


# ── Clients ───────────────────────────────────────────────────────────────────

def seed_clients(board_id: int, groups: dict):
    print("\n  Seeding: Clients")
    cm = col_map(board_id)

    items = [
        ("James Carter", "Active", {
            cm["Phone"]:           {"phone": "+14045550147", "countryShortName": "US"},
            cm["Email"]:           {"email": "james.carter@gmail.com", "text": "james.carter@gmail.com"},
            cm["Address"]:         "742 Magnolia St, Atlanta, GA 30301",
            cm["Language"]:        {"labels": ["English"]},
            cm["Client Since"]:    {"date": d(-365)},
            cm["Referral Source"]: "Attorney Marcus Webb",
            cm["Notes"]:           {"text": "Cooperative client. Paid retainer in full. Prefers contact via email."},
        }),
        ("Sofia Ramirez", "Active", {
            cm["Phone"]:           {"phone": "+17865550374", "countryShortName": "US"},
            cm["Email"]:           {"email": "sofia.ramirez@email.com", "text": "sofia.ramirez@email.com"},
            cm["Address"]:         "1801 SW 8th St, Miami, FL 33135",
            cm["Language"]:        {"labels": ["Spanish"]},
            cm["Client Since"]:    {"date": d(-90)},
            cm["Referral Source"]: "Elena Vasquez",
            cm["Notes"]:           {"text": "Requires Spanish interpreter for all proceedings. Sole custody of two children is top priority."},
        }),
        ("Elena Vasquez", "Active", {
            cm["Phone"]:           {"phone": "+13055550519", "countryShortName": "US"},
            cm["Email"]:           {"email": "elena.vasquez@email.com", "text": "elena.vasquez@email.com"},
            cm["Address"]:         "229 NW 2nd Ave, Miami, FL 33128",
            cm["Language"]:        {"labels": ["Spanish"]},
            cm["Client Since"]:    {"date": d(-180)},
            cm["Referral Source"]: "Walk-in",
            cm["Notes"]:           {"text": "Asylum petition pending. Very anxious about timeline. Call weekly with updates."},
        }),
        ("Robert Mensah", "Past", {
            cm["Phone"]:           {"phone": "+17705550632", "countryShortName": "US"},
            cm["Email"]:           {"email": "robert.mensah@email.com", "text": "robert.mensah@email.com"},
            cm["Address"]:         "45 Peachtree Rd NE, Atlanta, GA 30309",
            cm["Language"]:        {"labels": ["English"]},
            cm["Client Since"]:    {"date": d(-730)},
            cm["Referral Source"]: "Google Search",
            cm["Notes"]:           {"text": "Case closed - won. Excellent outcome. Strong referral candidate."},
        }),
        ("Kevin Wu", "Active", {
            cm["Phone"]:           {"phone": "+16175550428", "countryShortName": "US"},
            cm["Email"]:           {"email": "kevin.wu@email.com", "text": "kevin.wu@email.com"},
            cm["Address"]:         "88 Commonwealth Ave, Boston, MA 02116",
            cm["Language"]:        {"labels": ["English"]},
            cm["Client Since"]:    {"date": d(-8)},
            cm["Referral Source"]: "Walk-in",
            cm["Notes"]:           {"text": "First offense. Seeking diversion. Clean prior record, employed full-time."},
        }),
        ("Michael O'Brien", "Active", {
            cm["Phone"]:           {"phone": "+16175550743", "countryShortName": "US"},
            cm["Email"]:           {"email": "m.obrien@email.com", "text": "m.obrien@email.com"},
            cm["Address"]:         "310 Commonwealth Ave, Boston, MA 02115",
            cm["Language"]:        {"labels": ["English"]},
            cm["Client Since"]:    {"date": d(-10)},
            cm["Referral Source"]: "Attorney Referral",
            cm["Notes"]:           {"text": "High-net-worth divorce. Very detail-oriented. Wants written updates after every court appearance."},
        }),
    ]

    for name, status, cols in items:
        group_id = groups[status]
        item = mc.create_item(board_id, group_id, name, cols)
        print(f"    + {name} ({status}) — id={item.get('id')}")


# ── Cases ─────────────────────────────────────────────────────────────────────

def seed_cases(board_id: int, groups: dict):
    print("\n  Seeding: Cases")
    cm = col_map(board_id)

    items = [
        ("State v. Carter", "Open", {
            cm["Case Number"]:          "CR-2025-0412",
            cm["Case Type"]:            {"labels": ["Criminal Defense"]},
            cm["Sub-Type"]:             "DUI",
            cm["Status"]:               {"label": "Open"},
            cm["Court / Jurisdiction"]: "Fulton County Superior Court",
            cm["Filing Date"]:          {"date": d(-30)},
            cm["Next Hearing Date"]:    {"date": d(14)},
            cm["Retainer Amount"]:      5000,
            cm["Outstanding Balance"]:  0,
            cm["Priority"]:             {"labels": ["High"]},
            cm["Notes"]:                {"text": "DUI, BAC 0.12. Contesting breathalyzer calibration. Pre-trial motions filed. Arraignment scheduled."},
        }),
        ("In re: Ramirez Family", "In Progress", {
            cm["Case Number"]:          "FL-2025-0287",
            cm["Case Type"]:            {"labels": ["Family"]},
            cm["Sub-Type"]:             "Child Custody",
            cm["Status"]:               {"label": "In Progress"},
            cm["Court / Jurisdiction"]: "Miami-Dade Family Court",
            cm["Filing Date"]:          {"date": d(-60)},
            cm["Next Hearing Date"]:    {"date": d(21)},
            cm["Retainer Amount"]:      4500,
            cm["Outstanding Balance"]:  1500,
            cm["Priority"]:             {"labels": ["Medium"]},
            cm["Notes"]:                {"text": "Mediation scheduled. Father seeking joint custody. Mother requesting sole. GAL appointed for both children."},
        }),
        ("Vasquez Immigration Petition", "Pending Hearing", {
            cm["Case Number"]:          "IM-2025-0198",
            cm["Case Type"]:            {"labels": ["Immigration"]},
            cm["Sub-Type"]:             "Asylum",
            cm["Status"]:               {"label": "Pending Hearing"},
            cm["Court / Jurisdiction"]: "Miami Immigration Court",
            cm["Filing Date"]:          {"date": d(-90)},
            cm["Next Hearing Date"]:    {"date": d(12)},
            cm["Retainer Amount"]:      6000,
            cm["Outstanding Balance"]:  0,
            cm["Priority"]:             {"labels": ["Urgent"]},
            cm["Notes"]:                {"text": "Strong documentation package. UNHCR letter on file. Country conditions report submitted. Interpreter arranged."},
        }),
        ("State v. Mensah", "Closed", {
            cm["Case Number"]:          "CR-2024-0831",
            cm["Case Type"]:            {"labels": ["Criminal Defense"]},
            cm["Sub-Type"]:             "Drug Possession",
            cm["Status"]:               {"label": "Closed - Won"},
            cm["Court / Jurisdiction"]: "Fulton County Superior Court",
            cm["Filing Date"]:          {"date": d(-365)},
            cm["Next Hearing Date"]:    {"date": d(-30)},
            cm["Retainer Amount"]:      3500,
            cm["Outstanding Balance"]:  0,
            cm["Priority"]:             {"labels": ["Medium"]},
            cm["Notes"]:                {"text": "Charges dismissed after successful suppression motion. Evidence obtained via unlawful search. Case closed."},
        }),
        ("US v. Torres", "In Progress", {
            cm["Case Number"]:          "IM-2025-0356",
            cm["Case Type"]:            {"labels": ["Immigration"]},
            cm["Sub-Type"]:             "Deportation Defense",
            cm["Status"]:               {"label": "In Progress"},
            cm["Court / Jurisdiction"]: "US Immigration Court, Miami",
            cm["Filing Date"]:          {"date": d(-45)},
            cm["Next Hearing Date"]:    {"date": d(30)},
            cm["Retainer Amount"]:      8000,
            cm["Outstanding Balance"]:  2000,
            cm["Priority"]:             {"labels": ["High"]},
            cm["Notes"]:                {"text": "TPS application pending. Removal proceedings stayed. 3 US-born children. Brief filed arguing hardship."},
        }),
        ("State v. Williams", "Open", {
            cm["Case Number"]:          "CR-2025-0519",
            cm["Case Type"]:            {"labels": ["Criminal Defense"]},
            cm["Sub-Type"]:             "Assault",
            cm["Status"]:               {"label": "Open"},
            cm["Court / Jurisdiction"]: "Broward County Circuit Court",
            cm["Filing Date"]:          {"date": d(-15)},
            cm["Next Hearing Date"]:    {"date": d(25)},
            cm["Retainer Amount"]:      4000,
            cm["Outstanding Balance"]:  4000,
            cm["Priority"]:             {"labels": ["Medium"]},
            cm["Notes"]:                {"text": "Aggravated assault charge. Self-defense claim. Witness statements conflict. Police report requested."},
        }),
        ("Nguyen H1B Appeal", "Pending Hearing", {
            cm["Case Number"]:          "IM-2025-0441",
            cm["Case Type"]:            {"labels": ["Immigration"]},
            cm["Sub-Type"]:             "H1B Visa",
            cm["Status"]:               {"label": "Pending Hearing"},
            cm["Court / Jurisdiction"]: "USCIS Miami Field Office",
            cm["Filing Date"]:          {"date": d(-20)},
            cm["Next Hearing Date"]:    {"date": d(20)},
            cm["Retainer Amount"]:      3500,
            cm["Outstanding Balance"]:  500,
            cm["Priority"]:             {"labels": ["High"]},
            cm["Notes"]:                {"text": "Employer filed incorrect specialty occupation docs. RFE responded. USCIS interview scheduled. Strong employer letter."},
        }),
        ("State v. Brooks", "Closed", {
            cm["Case Number"]:          "CR-2024-0974",
            cm["Case Type"]:            {"labels": ["Criminal Defense"]},
            cm["Sub-Type"]:             "DUI",
            cm["Status"]:               {"label": "Closed - Settled"},
            cm["Court / Jurisdiction"]: "Palm Beach County Court",
            cm["Filing Date"]:          {"date": d(-400)},
            cm["Next Hearing Date"]:    {"date": d(-45)},
            cm["Retainer Amount"]:      2500,
            cm["Outstanding Balance"]:  0,
            cm["Priority"]:             {"labels": ["Low"]},
            cm["Notes"]:                {"text": "Plea deal accepted. 12-month probation, DUI school, license suspension 6 months. Client satisfied."},
        }),
        ("State v. Wu", "Open", {
            cm["Case Number"]:          "CR-2025-0608",
            cm["Case Type"]:            {"labels": ["Criminal Defense"]},
            cm["Sub-Type"]:             "Drug Possession",
            cm["Status"]:               {"label": "Open"},
            cm["Court / Jurisdiction"]: "Suffolk County District Court",
            cm["Filing Date"]:          {"date": d(-8)},
            cm["Next Hearing Date"]:    {"date": d(18)},
            cm["Retainer Amount"]:      3500,
            cm["Outstanding Balance"]:  0,
            cm["Priority"]:             {"labels": ["High"]},
            cm["Notes"]:                {"text": "First offense. Possession of 1.2g marijuana. Pursuing diversion program. Employer cannot know about charges."},
        }),
        ("O'Brien Divorce", "In Progress", {
            cm["Case Number"]:          "FL-2025-0334",
            cm["Case Type"]:            {"labels": ["Family"]},
            cm["Sub-Type"]:             "High-Asset Divorce",
            cm["Status"]:               {"label": "In Progress"},
            cm["Court / Jurisdiction"]: "Suffolk County Probate Court",
            cm["Filing Date"]:          {"date": d(-10)},
            cm["Next Hearing Date"]:    {"date": d(35)},
            cm["Retainer Amount"]:      12000,
            cm["Outstanding Balance"]:  7000,
            cm["Priority"]:             {"labels": ["High"]},
            cm["Notes"]:                {"text": "Joint business valued at $2.3M. Both parties have independent counsel. Business valuation expert retained."},
        }),
        ("State v. Jackson", "Pending Hearing", {
            cm["Case Number"]:          "CR-2025-0557",
            cm["Case Type"]:            {"labels": ["Criminal Defense"]},
            cm["Sub-Type"]:             "Assault",
            cm["Status"]:               {"label": "Pending Hearing"},
            cm["Court / Jurisdiction"]: "Orange County Circuit Court",
            cm["Filing Date"]:          {"date": d(-25)},
            cm["Next Hearing Date"]:    {"date": d(2)},
            cm["Retainer Amount"]:      4500,
            cm["Outstanding Balance"]:  1000,
            cm["Priority"]:             {"labels": ["Urgent"]},
            cm["Notes"]:                {"text": "Battery charge. Victim recanted but DA proceeding. Character witnesses lined up. Preliminary hearing imminent."},
        }),
        ("Adeyemi Asylum Case", "Open", {
            cm["Case Number"]:          "IM-2025-0489",
            cm["Case Type"]:            {"labels": ["Immigration"]},
            cm["Sub-Type"]:             "Political Asylum",
            cm["Status"]:               {"label": "Open"},
            cm["Court / Jurisdiction"]: "Baltimore Immigration Court",
            cm["Filing Date"]:          {"date": d(-5)},
            cm["Next Hearing Date"]:    {"date": d(45)},
            cm["Retainer Amount"]:      5500,
            cm["Outstanding Balance"]:  5500,
            cm["Priority"]:             {"labels": ["High"]},
            cm["Notes"]:                {"text": "Journalist fled Nigeria after death threats. Extensive documentation: newspaper articles, police reports, UNHCR letter."},
        }),
    ]

    for name, group_key, cols in items:
        group_id = groups[group_key]
        item = mc.create_item(board_id, group_id, name, cols)
        print(f"    + {name} ({group_key}) — id={item.get('id')}")


# ── Tasks ─────────────────────────────────────────────────────────────────────

def seed_tasks(board_id: int, groups: dict):
    print("\n  Seeding: Tasks")
    cm = col_map(board_id)

    items = [
        ("File motion to suppress — Carter",        "To Do",      "Filing",          "High",   5,   "Breathalyzer calibration records obtained. Motion drafted, needs attorney review before filing."),
        ("Prepare asylum documentation — Vasquez",  "To Do",      "Document Request","Urgent", 3,   "Compile UNHCR letter, country conditions report, and personal declaration. Hearing in 12 days."),
        ("Client follow-up call — Ramirez",         "Done",       "Client Follow-up","Medium", -2,  "Discussed mediation strategy. Client agreed to propose shared parenting schedule as fallback."),
        ("Gather witness statements — Williams",    "In Progress","Court Prep",       "High",   8,   "3 of 5 witnesses interviewed. Conflicting accounts on who initiated altercation. Continue interviews."),
        ("File I-485 form — Nguyen",                "To Do",      "Filing",           "Urgent", 7,   "Form complete. Employer authorization letter received. File by Friday to avoid OPT lapse."),
        ("Review plea agreement — Brooks",          "Done",       "Document Request", "Medium", -10, "Plea terms acceptable. 12 months probation agreed. Client signed. Filed with court."),
        ("Court prep for Torres hearing",           "In Progress","Court Prep",       "High",   6,   "Opening statement drafted. Hardship brief reviewed. Coordinate with interpreter for hearing."),
        ("Request police report — Williams",        "To Do",      "Document Request", "Low",    12,  "Submitted FOIA request. Expected within 10 business days. Follow up if not received."),
        ("Prepare sentencing memo — Wu",            "To Do",      "Court Prep",       "High",   10,  "Diversion program application submitted. Sentencing memo should highlight clean record and employment."),
        ("Interview character witnesses — Jackson", "In Progress","Court Prep",       "High",   1,   "Two witnesses confirmed. One outstanding. Victim recantation affidavit being notarized."),
        ("Draft settlement agreement — O'Brien",    "To Do",      "Filing",           "Medium", 20,  "Business valuation expert report due next week. Settlement terms being negotiated. Draft framework ready."),
        ("Submit petition for review — Vasquez",    "To Do",      "Filing",           "Urgent", 2,   "Petition for asylum review must be filed before hearing date. Attorney signature required."),
    ]

    STATUS_LABEL = {"To Do": "To Do", "In Progress": "In Progress", "Done": "Done"}

    for name, group_key, task_type, priority, due_offset, notes in items:
        group_id = groups[group_key]
        cols = {
            cm["Task Type"]:  {"labels": [task_type]},
            cm["Due Date"]:   {"date": d(due_offset)},
            cm["Priority"]:   {"labels": [priority]},
            cm["Status"]:     {"label": STATUS_LABEL[group_key]},
            cm["Notes"]:      {"text": notes},
        }
        item = mc.create_item(board_id, group_id, name, cols)
        print(f"    + {name} ({group_key}) — id={item.get('id')}")


# ── Hearings & Deadlines ──────────────────────────────────────────────────────

def seed_hearings(board_id: int, groups: dict):
    print("\n  Seeding: Hearings & Deadlines")
    cm = col_map(board_id)

    items = [
        ("Jackson Preliminary Hearing",  "This Week",  "Court Date",      2,  "Orange County Circuit Court, Rm 6A",           "Upcoming", "Defense counsel to present recantation affidavit. Arrive 30 min early."),
        ("Torres Status Conference",     "This Week",  "Court Date",      3,  "US Immigration Court, Miami, Courtroom 3",     "Upcoming", "Update on TPS application. Interpreter confirmed. Bring hardship documentation."),
        ("Carter Arraignment",           "This Week",  "Court Date",      5,  "Fulton County Superior Court, Rm 4B",          "Upcoming", "Plea of not guilty to be entered. Bail review possible. Client briefed."),
        ("Vasquez Asylum Hearing",       "This Month", "Court Date",      12, "Miami Immigration Court, 333 S. Miami Ave",    "Upcoming", "Full merits hearing. Interpreter arranged. All documentation submitted."),
        ("Ramirez Mediation Session",    "This Month", "Mediation",       8,  "Zoom — link sent to client",                   "Upcoming", "Both parties' counsel attending. GAL report expected same day."),
        ("Wu Arraignment",               "This Month", "Court Date",      10, "Suffolk County District Court, Courtroom 1",   "Upcoming", "Entering not guilty plea. Diversion program referral to be requested."),
        ("Nguyen USCIS Interview",       "Upcoming",   "Client Meeting",  20, "USCIS Miami Field Office, 8th Floor",          "Upcoming", "Prep session scheduled day before. Bring original I-797, passport, employer letter."),
        ("O'Brien Discovery Deadline",   "Upcoming",   "Filing Deadline", 25, "Suffolk County Probate Court",                 "Upcoming", "All financial disclosures due. Business valuation report must be filed by this date."),
    ]

    for name, group_key, hearing_type, date_offset, location, status, notes in items:
        group_id = groups[group_key]
        cols = {
            cm["Hearing Type"]:   {"labels": [hearing_type]},
            cm["Date & Time"]:    {"date": d(date_offset)},
            cm["Location / Link"]:location,
            cm["Status"]:         {"label": status},
            cm["Notes"]:          {"text": notes},
        }
        item = mc.create_item(board_id, group_id, name, cols)
        print(f"    + {name} ({group_key}) — id={item.get('id')}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Law Firm CRM — Seeding Dummy Data")
    print("=" * 60)

    config = load_config()
    boards = config["boards"]

    seed_intake(   boards["Intake"]["id"],   boards["Intake"]["groups"])
    seed_clients(  boards["Clients"]["id"],  boards["Clients"]["groups"])
    seed_cases(    boards["Cases"]["id"],    boards["Cases"]["groups"])
    seed_tasks(    boards["Tasks"]["id"],    boards["Tasks"]["groups"])
    seed_hearings( boards["Hearings"]["id"], boards["Hearings"]["groups"])

    print(f"\n{'='*60}")
    print("Done! All boards fully populated.")
    print("Open Monday.com → Law Firm CRM workspace to verify.")


if __name__ == "__main__":
    main()
