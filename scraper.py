import pandas as pd
from jobspy import scrape_jobs
import firebase_admin
from firebase_admin import credentials, firestore
from playwright.sync_api import sync_playwright
import os, json, time, random
import urllib.parse

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
    print(f"🤖 [ROBOT] Mode Debug HTML activé...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        
        # Injection des cookies
        cookies_json = os.getenv('JOBTEASER_COOKIES')
        if cookies_json:
            context.add_cookies(json.loads(cookies_json))

        page = context.new_page()
        
        try:
            for kw in keywords:
                # Encodage propre du mot-clé
                kw_encoded = urllib.parse.quote_plus(kw)
                search_url = f"https://ec-lyon.jobteaser.com/fr/job-offers?query={kw_encoded}"
                
                print(f"\n--- 🔎 RECHERCHE : {kw} ---")
                page.goto(search_url, wait_until="commit")
                
                # On attend un peu que le JS s'exécute
                time.sleep(7)
                
                # --- EXTRACTION DU HTML POUR DEBUG ---
                current_html = page.content()
                print(f"🤖 [DEBUG] URL actuelle : {page.url}")
                print(f"🤖 [DEBUG] Titre de la page : {page.title()}")
                print(f"🤖 [DEBUG] Extrait du code HTML (5000 chars) :\n")
                print(current_html[:5000]) # On affiche le début du code source
                print(f"\n--- FIN DE L'EXTRAIT ---")

                # Tentative d'extraction des offres
                # On cherche les liens d'offres (méthode robuste)
                offers_links = page.locator('a[href*="/fr/job-offers/"]').all()
                
                # Filtrage des liens uniques et longs (les vraies offres)
                unique_hrefs = set()
                count_found = 0
                
                for link_el in offers_links:
                    href = link_el.get_attribute('href')
                    if href and href not in unique_hrefs and len(href) > 35:
                        unique_hrefs.add(href)
                        try:
                            # Tentative de récupération du titre dans le lien ou son parent
                            title = link_el.inner_text().split('\n')[0].strip()
                            if not title: continue
                            
                            full_link = f"https://ec-lyon.jobteaser.com{href}" if href.startswith('/') else href
                            
                            results.append({
                                'title': title,
                                'company': "Vérifier HTML debug",
                                'location': 'Exclu JobTeaser',
                                'job_url': full_link,
                                'site': 'jobteaser'
                            })
                            count_found += 1
                        except: continue
                
                print(f"🎯 Résultat : {count_found} offres identifiées via les liens.")

        except Exception as e:
            print(f"❌ Erreur critique : {e}")
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
