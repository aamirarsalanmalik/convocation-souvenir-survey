import json
import os
from datetime import datetime
import pandas as pd
import streamlit as st

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


def init_state():
    if "submitted" not in st.session_state:
        st.session_state.submitted = False


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


def save_responses(student_info, selections):
    rows = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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

    df = pd.DataFrame(rows)

    if os.path.exists(RESPONSES_FILE):
        old = pd.read_csv(RESPONSES_FILE)
        df = pd.concat([old, df], ignore_index=True)

    df.to_csv(RESPONSES_FILE, index=False)


def render_summary(selections):
    if selections:
        st.subheader("Current Selections")
        summary_df = pd.DataFrame(selections)
        st.dataframe(summary_df, use_container_width=True, hide_index=True)


def render_admin_preview():
    with st.expander("Admin Preview: See collected results from this demo"):
        if os.path.exists(RESPONSES_FILE):
            df = pd.read_csv(RESPONSES_FILE)
            st.dataframe(df, use_container_width=True, hide_index=True)

            st.markdown("**Product counts**")
            st.bar_chart(df["product"].value_counts())

            st.markdown("**Design counts**")
            design_counts = df.groupby(["product", "design"]).size().reset_index(name="votes")
            st.dataframe(design_counts, use_container_width=True, hide_index=True)
        else:
            st.write("No responses saved yet.")


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
            save_responses(student_info, selections)
            st.success("Your response has been submitted successfully.")
            st.balloons()
        else:
            st.error(message)

    render_admin_preview()


if __name__ == "__main__":
    main()
