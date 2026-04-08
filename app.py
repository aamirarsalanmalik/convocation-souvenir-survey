import json
import os
from datetime import datetime
from io import BytesIO

import pandas as pd
import streamlit as st

try:
    import gspread
    from google.oauth2.service_account import Credentials
except Exception:  # pragma: no cover
    gspread = None
    Credentials = None

st.set_page_config(
    page_title="Convocation Souvenir Survey",
    page_icon="🎓",
    layout="wide",
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, "data", "products.json")
RESPONSES_DIR = os.path.join(BASE_DIR, "responses")
RESPONSES_FILE = os.path.join(RESPONSES_DIR, "votes.csv")

os.makedirs(RESPONSES_DIR, exist_ok=True)

with open(DATA_PATH, "r", encoding="utf-8") as f:
    PRODUCTS = json.load(f)

GSHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

EXPECTED_HEADERS = [
    "timestamp",
    "name",
    "department",
    "batch",
    "email_or_rollno",
    "product",
    "design",
    "price",
]


@st.cache_resource
def get_gspread_client():
    """Return an authenticated gspread client if secrets are configured."""
    if gspread is None or Credentials is None:
        return None

    if "gcp_service_account" not in st.secrets or "google_sheet" not in st.secrets:
        return None

    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=GSHEETS_SCOPES)
    return gspread.authorize(creds)


@st.cache_resource
def get_gsheet_worksheet():
    client = get_gspread_client()
    if client is None:
        return None

    google_sheet = st.secrets["google_sheet"]
    sheet_name = google_sheet.get("spreadsheet_name")
    worksheet_name = google_sheet.get("worksheet_name", "responses")

    if not sheet_name:
        return None

    spreadsheet = client.open(sheet_name)

    try:
        worksheet = spreadsheet.worksheet(worksheet_name)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows=1000, cols=20)

    current_headers = worksheet.row_values(1)
    if current_headers != EXPECTED_HEADERS:
        worksheet.update("A1:H1", [EXPECTED_HEADERS])

    return worksheet


def init_state():
    defaults = {
        "submitted": False,
        "admin_authenticated": False,
        "admin_login_attempted": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value



def render_header():
    st.title("🎓 Convocation Souvenir Preference Survey")
    st.write(
        "Select the products you are interested in. Once you select a product, "
        "its available designs will appear immediately below it."
    )
    st.info("Prices are shown at the main product level, exactly as required.")



def render_student_info():
    st.subheader("Student Information")
    c1, c2 = st.columns(2)
    with c1:
        name = st.text_input("Full Name *", key="student_name")
        department = st.text_input("Department *", key="student_department")
    with c2:
        batch = st.text_input("Batch / Program *", key="student_batch")
        email = st.text_input("Email or Roll Number *", key="student_email")
    return {
        "name": name.strip(),
        "department": department.strip(),
        "batch": batch.strip(),
        "email": email.strip(),
    }



def render_product_card(product_name, product):
    st.markdown("---")
    col1, col2 = st.columns([1, 1.2])

    with col1:
        main_img = os.path.join(BASE_DIR, product["main_image"])
        st.image(main_img, use_container_width=True)

    with col2:
        st.subheader(product_name)
        st.markdown(f"**Price:** Rs. {product['price']}")
        st.write(product.get("description", ""))

        interest_key = f"interest_{product_name}"
        design_key = f"design_{product_name}"

        interested = st.checkbox(
            f"I am interested in {product_name}",
            key=interest_key,
        )

        if interested:
            st.success(f"{product_name} selected. Please choose one design below.")

            design_names = list(product["designs"].keys())
            img_cols = st.columns(len(design_names))

            for i, design_name in enumerate(design_names):
                with img_cols[i]:
                    design_img = os.path.join(BASE_DIR, product["designs"][design_name])
                    st.image(design_img, caption=design_name, use_container_width=True)

            st.radio(
                f"Choose your preferred design for {product_name}",
                options=design_names,
                key=design_key,
                horizontal=True if len(design_names) <= 3 else False,
            )
        else:
            if design_key in st.session_state:
                del st.session_state[design_key]



def collect_selected_products():
    selections = []
    for product_name in PRODUCTS:
        if st.session_state.get(f"interest_{product_name}", False):
            selected_design = st.session_state.get(f"design_{product_name}", "")
            selections.append({
                "product": product_name,
                "design": selected_design,
                "price": PRODUCTS[product_name]["price"],
            })
    return selections



def validate_response(student_info, selections):
    missing = []
    for key, label in [
        ("name", "Full Name"),
        ("department", "Department"),
        ("batch", "Batch / Program"),
        ("email", "Email or Roll Number"),
    ]:
        if not student_info[key]:
            missing.append(label)

    if missing:
        return False, f"Please fill these required fields: {', '.join(missing)}"

    if not selections:
        return False, "Please select at least one product."

    missing_designs = [s["product"] for s in selections if not s["design"]]
    if missing_designs:
        return False, "Please choose one design for: " + ", ".join(missing_designs)

    return True, ""



def build_rows(student_info, selections):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for item in selections:
        rows.append({
            "timestamp": timestamp,
            "name": student_info["name"],
            "department": student_info["department"],
            "batch": student_info["batch"],
            "email_or_rollno": student_info["email"],
            "product": item["product"],
            "design": item["design"],
            "price": item["price"],
        })
    return rows



def save_to_local_csv(rows):
    df = pd.DataFrame(rows)
    if os.path.exists(RESPONSES_FILE):
        old = pd.read_csv(RESPONSES_FILE)
        df = pd.concat([old, df], ignore_index=True)
    df.to_csv(RESPONSES_FILE, index=False)



def save_to_google_sheets(rows):
    worksheet = get_gsheet_worksheet()
    if worksheet is None:
        return False, "Google Sheets is not configured yet."

    ordered_rows = [
        [
            row["timestamp"],
            row["name"],
            row["department"],
            row["batch"],
            row["email_or_rollno"],
            row["product"],
            row["design"],
            row["price"],
        ]
        for row in rows
    ]
    worksheet.append_rows(ordered_rows, value_input_option="USER_ENTERED")
    return True, "Saved to Google Sheets."



def save_responses(student_info, selections):
    rows = build_rows(student_info, selections)
    save_to_local_csv(rows)
    sheets_ok, sheets_msg = save_to_google_sheets(rows)
    return sheets_ok, sheets_msg



def render_summary(selections):
    if selections:
        st.subheader("Current Selections")
        summary_df = pd.DataFrame(selections)
        st.dataframe(summary_df, use_container_width=True, hide_index=True)



def get_admin_config():
    admin_password = None
    admin_emails = []
    if "admin" in st.secrets:
        admin_password = st.secrets["admin"].get("password")
        admin_emails_raw = st.secrets["admin"].get("emails", [])
        admin_emails = [str(x).strip().lower() for x in admin_emails_raw if str(x).strip()]
    return admin_password, admin_emails



def render_admin_access_panel():
    st.markdown("---")
    with st.expander("🔒 Admin Access", expanded=False):
        st.caption("Only admins can unlock the response download area.")

        admin_password, admin_emails = get_admin_config()

        if not admin_password:
            st.warning("Admin download is disabled until admin secrets are configured.")
            return False

        if st.session_state.admin_authenticated:
            st.success("Admin authenticated. Download tools are now available below.")
            if st.button("Log out admin", key="admin_logout_main"):
                st.session_state.admin_authenticated = False
                st.rerun()
            return True

        c1, c2 = st.columns(2)
        with c1:
            entered_email = st.text_input("Admin email", key="admin_email_input")
        with c2:
            entered_password = st.text_input("Admin password", type="password", key="admin_password_input")

        if st.button("Unlock admin tools", key="admin_login_btn_main", use_container_width=True):
            email_clean = entered_email.strip().lower()
            password_ok = entered_password == admin_password
            email_ok = True if not admin_emails else email_clean in admin_emails

            st.session_state.admin_login_attempted = True
            st.session_state.admin_authenticated = bool(password_ok and email_ok)

            if not password_ok:
                st.error("Incorrect admin password.")
            elif not email_ok:
                st.error("This email is not allowed for admin access.")
            else:
                st.success("Admin access granted.")
                st.rerun()

    return st.session_state.admin_authenticated



def fetch_google_sheet_df():
    worksheet = get_gsheet_worksheet()
    if worksheet is None:
        return None

    records = worksheet.get_all_records()
    if not records:
        return pd.DataFrame(columns=EXPECTED_HEADERS)
    return pd.DataFrame(records)



def get_local_df():
    if os.path.exists(RESPONSES_FILE):
        return pd.read_csv(RESPONSES_FILE)
    return pd.DataFrame(columns=EXPECTED_HEADERS)



def render_admin_tools(admin_authenticated):
    if not admin_authenticated:
        return

    st.markdown("---")
    st.subheader("Admin Download Center")
    st.caption("Only authenticated admins can view and download recorded responses.")

    source = st.radio(
        "Choose response source",
        options=["Local CSV", "Google Sheets"],
        horizontal=True,
        key="admin_download_source",
    )

    if source == "Google Sheets":
        df = fetch_google_sheet_df()
        if df is None:
            st.warning("Google Sheets is not configured or could not be reached.")
            return
    else:
        df = get_local_df()

    if df.empty:
        st.info("No responses available yet.")
        return

    st.dataframe(df, use_container_width=True, hide_index=True)

    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download responses as CSV",
        data=csv_bytes,
        file_name="souvenir_responses.csv",
        mime="text/csv",
        key="download_responses_csv",
        use_container_width=True,
    )

    xlsx_buffer = BytesIO()
    with pd.ExcelWriter(xlsx_buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="responses")
    st.download_button(
        label="Download responses as Excel",
        data=xlsx_buffer.getvalue(),
        file_name="souvenir_responses.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_responses_excel",
        use_container_width=True,
    )

    st.markdown("**Product vote counts**")
    st.bar_chart(df["product"].value_counts())

    st.markdown("**Design vote counts**")
    design_counts = df.groupby(["product", "design"]).size().reset_index(name="votes")
    st.dataframe(design_counts, use_container_width=True, hide_index=True)



def render_setup_help():
    with st.expander("Google Sheets and admin setup help"):
        st.markdown(
            """
1. Create a Google Cloud project and enable **Google Sheets API** and **Google Drive API**.
2. Create a **Service Account** and download its JSON key.
3. Share your target Google Sheet with the service account email.
4. In Streamlit Community Cloud, open **App settings → Secrets** and paste secrets in TOML format.
5. Add your admin password and optional admin emails in the same secrets panel.
            """
        )
        st.code(
            """
[gcp_service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "your-private-key-id"
private_key = "-----BEGIN PRIVATE KEY-----
YOUR_KEY
-----END PRIVATE KEY-----
"
client_email = "your-service-account@your-project.iam.gserviceaccount.com"
client_id = "1234567890"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/your-service-account%40your-project.iam.gserviceaccount.com"
universe_domain = "googleapis.com"

[google_sheet]
spreadsheet_name = "Souvenir Survey Responses"
worksheet_name = "responses"

[admin]
password = "change-this-password"
emails = ["admin1@university.edu", "admin2@university.edu"]
            """,
            language="toml",
        )



def main():
    init_state()
    render_header()
    student_info = render_student_info()

    st.subheader("Choose Souvenir Products and Designs")
    for product_name, product in PRODUCTS.items():
        render_product_card(product_name, product)

    selections = collect_selected_products()
    render_summary(selections)

    if st.button("Submit Vote", type="primary", use_container_width=True):
        valid, message = validate_response(student_info, selections)
        if valid:
            sheets_ok, sheets_msg = save_responses(student_info, selections)
            st.success("Your response has been submitted successfully.")
            if sheets_ok:
                st.caption("Saved to local CSV and Google Sheets.")
            else:
                st.warning(f"Saved to local CSV only. {sheets_msg}")
            st.balloons()
        else:
            st.error(message)

    admin_authenticated = render_admin_access_panel()
    render_admin_tools(admin_authenticated)
    render_setup_help()


if __name__ == "__main__":
    main()
