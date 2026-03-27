import pandas as pd
from jobspy import scrape_jobs
import firebase_admin
from firebase_admin import credentials, firestore
from playwright.sync_api import sync_playwright
import os, json, time, random, urllib.parse

# --- 1. INITIALISATION FIREBASE ---
def init_firebase():
    if not firebase_admin._apps:
        try:
            service_account_info = json.loads(os.getenv('FIREBASE_SERVICE_ACCOUNT'))
            cred = credentials.Certificate(service_account_info)
            firebase_admin.initialize_app(cred)
        except: pass
    return firestore.client()

# --- 2. FONCTION SCRAPING JOBTEASER ---
def scrape_jobteaser(email, password, keywords):
    results = []
    print(f"🤖 [ROBOT] Tentative par URL Directe (Bypass Interface)...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled'])
        # On définit un contexte avec des permissions pour éviter les popups
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            java_script_enabled=True
        )
        
        # Injection des cookies
        cookies_json = os.getenv('JOBTEASER_COOKIES')
        if cookies_json:
            context.add_cookies(json.loads(cookies_json))

        page = context.new_page()
        page.add_init_script("delete navigator.__proto__.webdriver")

        try:
            for kw in keywords:
                # On utilise l'URL directe que tu as validée
                kw_encoded = urllib.parse.quote_plus(kw)
                # URL spécifique au portail EC-LYON
                target_url = f"https://ec-lyon.jobteaser.com/fr/job-offers?query={kw_encoded}"
                
                print(f"--- 🔎 URL : {target_url} ---")
                page.goto(target_url, wait_until="commit")
                
                # On attend 8 secondes (JobTeaser est lent à charger ses offres via API)
                time.sleep(8)

                # Si on voit "Just a moment", on attend encore un peu
                if "Just a moment" in page.title():
                    print("⚠️ Cloudflare challenge en cours... patience.")
                    time.sleep(10)

                # Extraction via les sélecteurs Skiller de ton HTML debug
                offers = page.locator('a[class*="sk-Card_main"]').all()
                
                if not offers:
                    # Sélecteur de secours : tous les liens d'offres
                    offers = page.locator('a[href*="/fr/job-offers/"]').all()

                print(f"🎯 {len(offers)} éléments détectés.")

                for offer in offers:
                    try:
                        # Extraction du titre (cherche le h3 à l'intérieur)
                        title = offer.locator('h3').first.inner_text()
                        # Entreprise (via testid)
                        company = offer.locator('[data-testid="jobad-card-company-name"]').first.inner_text()
                        href = offer.get_attribute('href')
                        
                        if title and company and href:
                            results.append({
                                'title': title.strip(),
                                'company': company.strip(),
                                'location': 'JobTeaser (ENISE)',
                                'job_url': f"https://ec-lyon.jobteaser.com{href}" if href.startswith('/') else href,
                                'site': 'jobteaser'
                            })
                    except: continue

        except Exception as e:
            print(f"❌ Erreur : {e}")
        finally:
            browser.close()
            
    return results

# --- 3. EXECUTION PRINCIPALE ---
if __name__ == "__main__":
    db = init_firebase()
    USERS = {"baptiste.mocydlarz@etu-enise.ec-lyon.fr": {"villes": ["Saint-Étienne", "Lille"], "dist": 30}}
    MOTS_CLES = ["Stage Génie Mécanique", "Stage Conception CAO", "Stage Industrialisation", "Stage R&D"]
    JT_PASS = os.getenv('JOBTEASER_PASS')

    for email, prefs in USERS.items():
        all_results = []
        
        # A. Public
        print(f"🔎 Scraping Public pour {email}...")
        for loc in prefs["villes"]:
            for kw in MOTS_CLES:
                try:
                    jobs = scrape_jobs(site_name=["linkedin", "indeed"], search_term=kw, location=f"{loc}, France", distance=prefs["dist"], results_wanted=8, hours_old=336, country_indeed='france')
                    if not jobs.empty: all_results.append(jobs)
                except: continue

        # B. JobTeaser
        if JT_PASS:
            jt_data = scrape_jobteaser(email, JT_PASS, MOTS_CLES)
            if jt_data: all_results.append(pd.DataFrame(jt_data))

        # C. Firebase
        if all_results:
            final_df = pd.concat(all_results).drop_duplicates(subset=['job_url'])
            db.collection('jobs').document(email.lower()).set({
                'offers': final_df.astype(str).to_dict(orient='records'),
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            print(f"✨ Terminé ! {len(final_df)} offres stockées.")
