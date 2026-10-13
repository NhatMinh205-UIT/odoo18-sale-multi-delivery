import re
import sys
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8171"
results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)


def pick_many2one(page, field_sel, text, option_text=None):
    inp = page.locator(f"{field_sel} input").first
    inp.click()
    inp.fill(text)
    page.wait_for_timeout(700)
    opt = page.locator(".o-autocomplete--dropdown-item", has_text=option_text or text).first
    opt.click()
    page.wait_for_timeout(400)


def dropdown_options(page, field_sel, text=""):
    inp = page.locator(f"{field_sel} input").first
    inp.click()
    inp.fill(text)
    page.wait_for_timeout(900)
    opts = [o.inner_text().strip() for o in page.locator(".o-autocomplete--dropdown-item").all()]
    inp.fill("")
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    return opts


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1500, "height": 1000})
    page.set_default_timeout(15000)
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.goto(f"{BASE}/web/login?db=multi_delivery_poc")
    page.fill("input[name=login]", "admin")
    page.fill("input[name=password]", "admin")
    page.click("button[type=submit]")
    page.wait_for_selector(".o_navbar, .o_main_navbar")
    check("UI-01 login", True)

    page.goto(f"{BASE}/odoo/action-sale.action_quotations_with_onboarding/new")
    page.wait_for_selector(".o_form_view")
    pick_many2one(page, ".o_field_widget[name=partner_id]", "Acme Corporation")
    check("UI-02 customer selected", "Acme" in page.locator(".o_field_widget[name=partner_id] input").input_value())

    # Line 1
    page.locator(".o_field_x2many_list_row_add a", has_text="Add a product").click()
    page.wait_for_timeout(500)
    row = page.locator(".o_data_row.o_selected_row, .o_data_row").last
    pick_many2one(page, ".o_selected_row div[name=product_template_id]", "Laptop UI")
    qty = page.locator(".o_selected_row div[name=product_uom_qty] input")
    qty.fill("4")

    addr_sel = ".o_selected_row div[name=dest_address_id]"
    check("UI-03 dest address column present", page.locator(addr_sel).count() == 1)
    opts = dropdown_options(page, addr_sel)
    print("   dropdown options:", opts)
    check("UI-04 dropdown lists Acme addresses",
          all(any(f"Office {k}" in o for o in opts) for k in "ABC"), str(opts))
    check("UI-05 dropdown hides other customer's address",
          not any("OtherUI" in o for o in opts))
    opts2 = dropdown_options(page, addr_sel, "OtherUI")
    existing = [o for o in opts2 if not o.startswith("Create") and o not in ("Search More...", "Start typing...")]
    check("UI-06 searching other customer's address finds no existing record",
          not existing, str(opts2))
    pick_many2one(page, addr_sel, "Office A")

    # Lines 2 and 3
    for key, q in (("B", "3"), ("C", "3")):
        page.locator(".o_field_x2many_list_row_add a", has_text="Add a product").click()
        page.wait_for_timeout(500)
        pick_many2one(page, ".o_selected_row div[name=product_template_id]", "Laptop UI")
        page.locator(".o_selected_row div[name=product_uom_qty] input").fill(q)
        pick_many2one(page, ".o_selected_row div[name=dest_address_id]", f"Office {key}")

    page.locator(".o_form_view .o_form_sheet").click(position={"x": 5, "y": 5})
    page.wait_for_timeout(500)
    page.locator("button.o_form_button_save").click()
    page.wait_for_timeout(1200)
    n_lines = page.locator(".o_data_row").count()
    check("UI-07 order saved with 3 lines", n_lines == 3, f"lines={n_lines}")

    page.locator("button[name=action_confirm]").first.click()
    page.wait_for_timeout(2500)
    state_txt = page.locator(".o_statusbar_status .o_arrow_button_current").inner_text().strip()
    check("UI-08 order confirmed", "Sales Order" in state_txt, state_txt)

    btn = page.locator("button[name=action_view_delivery]")
    btn_txt = btn.inner_text().replace("\n", " ").strip() if btn.count() else "missing"
    check("UI-09 Delivery smart button shows 3", btn.count() == 1 and "3" in btn_txt, btn_txt)

    # After confirm: address of existing lines is read-only
    first_addr_cell = page.locator(".o_data_row").first.locator("td[name=dest_address_id]")
    first_addr_cell.click()
    page.wait_for_timeout(600)
    editable = page.locator(".o_selected_row div[name=dest_address_id] input").count()
    check("UI-10 address read-only after confirm", editable == 0, f"inputs={editable}")
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    # Open deliveries
    btn.click()
    page.wait_for_selector(".o_list_view, .o_kanban_view")
    page.wait_for_timeout(1000)
    rows = [r.inner_text().replace("\n", " | ") for r in page.locator(".o_data_row").all()]
    for r in rows:
        print("   picking row:", r)
    check("UI-11 three delivery orders listed", len(rows) == 3, f"rows={len(rows)}")
    for key in "ABC":
        check(f"UI-12 delivery for Office {key} present", any(f"Office {key}" in r for r in rows))

    # Server-side validation seen through the UI: quick-create an address that is not the customer's
    page.goto(f"{BASE}/odoo/action-sale.action_quotations_with_onboarding/new")
    page.wait_for_selector(".o_form_view")
    pick_many2one(page, ".o_field_widget[name=partner_id]", "Acme Corporation")
    page.locator(".o_field_x2many_list_row_add a", has_text="Add a product").click()
    page.wait_for_timeout(500)
    pick_many2one(page, ".o_selected_row div[name=product_template_id]", "Laptop UI")
    inp = page.locator(".o_selected_row div[name=dest_address_id] input")
    inp.click()
    inp.fill("ZZ Stranger Address")
    page.wait_for_timeout(800)
    page.locator(".o-autocomplete--dropdown-item", has_text="Create").first.click()
    page.wait_for_timeout(800)
    page.locator(".o_form_view .o_form_sheet").click(position={"x": 5, "y": 5})
    page.locator("button.o_form_button_save").click()
    page.wait_for_timeout(1500)
    dialog = page.locator(".modal-body")
    msg = dialog.first.inner_text().replace("\n", " ") if dialog.count() else ""
    check("UI-14 foreign address rejected on save with clear message",
          "not a valid delivery address" in msg, msg[:200])

    check("UI-13 no JS page errors", not errors, "; ".join(errors)[:300])
    browser.close()

failed = [r for r in results if not r[1]]
print(f"\nSUMMARY: {len(results) - len(failed)} PASS / {len(failed)} FAIL of {len(results)}")
sys.exit(1 if failed else 0)
