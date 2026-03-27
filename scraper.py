import pandas as pd
from jobspy import scrape_jobs
import firebase_admin
from firebase_admin import credentials, firestore
from playwright.sync_api import sync_playwright
import os, json, time, random

# --- 1. INITIALISATION FIREBASE ---
def init_firebase():
    if not firebase_admin._apps:
        service_account_info = json.loads(os.getenv('FIREBASE_SERVICE_ACCOUNT'))
        cred = credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(cred)
    return firestore.client()

# --- 2. FONCTION SCRAPING JOBTEASER ---
def scrape_jobteaser(email, password, keywords):
    results = []
    print(f"🤖 [ROBOT] Tentative d'accès direct au flux école...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled'])
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
        page = context.new_page()
        page.add_init_script("delete navigator.__proto__.webdriver")

        try:
            # 1. Connexion (Obligatoire pour avoir le cookie de session)
            page.goto("https://ec-lyon.jobteaser.com/fr/users/sign_in")
            page.fill('input[type="email"]', email)
            page.fill('input[type="password"]', password)
            page.keyboard.press("Enter")
            page.wait_for_url("**/dashboard**", timeout=30000)
            print("✅ Session école ouverte.")

            # 2. On attend un peu sur le dashboard pour "chauffer" la session
            time.sleep(5)

            # 3. On tente l'accès direct à ton URL spécifique
            # On utilise domcontentloaded pour être plus rapide que le script de blocage Cloudflare
            target_url = "https://ec-lyon.jobteaser.com/fr/job-offers?query=Stage+R&q=stage+genie+m%C3%A9canique"
            print(f"🤖 [ROBOT] Navigation directe vers : {target_url}")
            
            page.goto(target_url, wait_until="domcontentloaded")
            
            # On attend 10 secondes pour laisser Cloudflare passer ou les offres charger
            time.sleep(10)
            
            print(f"🤖 [ROBOT] Page chargée. Titre : {page.title()}")

            # Si Cloudflare est là, on tente un "clic" au milieu de l'écran (parfois ça valide le challenge)
            if "Just a moment" in page.title():
                print("⚠️ Cloudflare détecté. Tentative de clic de validation...")
                page.mouse.click(200, 200)
                time.sleep(5)

            # 4. Extraction des offres
            if page.locator("article").count() > 0:
                offers = page.locator("article").all()
                print(f"✨ SUCCÈS : {len(offers)} offres trouvées !")
                for offer in offers:
                    try:
                        title = offer.locator('h2, h3').first.inner_text()
                        company = offer.locator('p').first.inner_text()
                        link = offer.locator('a').first.get_attribute('href')
                        results.append({
                            'title': title.strip(),
                            'company': company.strip(),
                            'location': 'Exclu JobTeaser (ENISE)',
                            'job_url': f"https://ec-lyon.jobteaser.com{link}" if link.startswith('/') else link,
                            'site': 'jobteaser'
                        })
                    except: continue
            else:
                print("❌ Toujours aucune offre visible. Cloudflare a gagné cette manche.")

        except Exception as e:
            print(f"❌ Erreur : {e}")
        finally:
            browser.close()
    return results

# --- 3. EXECUTION PRINCIPALE ---
if __name__ == "__main__":
    db = init_firebase()
    
    USERS = {
        "baptiste.mocydlarz@etu-enise.ec-lyon.fr": {"villes": ["Saint-Étienne", "Lille"], "dist": 30}
    }

    MOTS_CLES = ["Stage Génie Mécanique", "Stage Conception CAO", "Stage Industrialisation", "Stage R&D"]
    JT_PASS = os.getenv('JOBTEASER_PASS')

    for email, prefs in USERS.items():
        all_results = []

        # A. JobSpy (LinkedIn/Indeed)
        print(f"🔎 Scraping Public pour {email}...")
        for loc in prefs["villes"]:
            for kw in MOTS_CLES:
                try:
                    jobs = scrape_jobs(
                        site_name=["linkedin", "indeed"],
                        search_term=kw,
                        location=f"{loc}, France",
                        distance=prefs["dist"],
                        results_wanted=15,
                        hours_old=336,
                        country_indeed='france'
                    )
                    if not jobs.empty: all_results.append(jobs)
                except: continue

        # B. JobTeaser (Furtif)
        if JT_PASS:
            jt_data = scrape_jobteaser(email, JT_PASS, MOTS_CLES)
            if jt_data: all_results.append(pd.DataFrame(jt_data))

        # C. Firebase
        if all_results:
            final_df = pd.concat(all_results).drop_duplicates(subset=['job_url'])
            final_df = final_df.astype(str)
            db.collection('jobs').document(email.lower()).set({
                'offers': final_df.to_dict(orient='records'),
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            print(f"✨ Terminé ! {len(final_df)} offres stockées.")
