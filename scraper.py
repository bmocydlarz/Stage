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
            print("✅ Firebase initialisé.")
        except Exception as e:
            print(f"❌ Erreur initialisation Firebase : {e}")
    return firestore.client()

# --- 2. FONCTION SCRAPING JOBTEASER (ANTI-TIMEOUT) ---
def scrape_jobteaser(email, password, keywords):
    results = []
    print(f"🤖 [ROBOT] Démarrage du module Haute-Fidélité (V-Fast)...")
    
    with sync_playwright() as p:
        # Lancement furtif
        browser = p.chromium.launch(headless=True, args=[
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox'
        ])
        
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
        
        page = context.new_page()
        page.add_init_script("delete navigator.__proto__.webdriver")
        
        # Injection des cookies (Session Baptiste)
        cookies_json = os.getenv('JOBTEASER_COOKIES')
        if cookies_json:
            try:
                context.add_cookies(json.loads(cookies_json))
                print("✅ Cookies de session injectés.")
            except Exception as e:
                print(f"⚠️ Erreur format cookies : {e}")

        try:
            # ÉTAPE 1 : Accès Dashboard (Rapide)
            print("🤖 [ROBOT] Connexion au portail école...")
            page.goto("https://ec-lyon.jobteaser.com/fr/dashboard", wait_until="commit")
            time.sleep(4) # Pause fixe plus fiable que networkidle

            # ÉTAPE 2 : Accès direct à la page des offres
            print("🤖 [ROBOT] Accès à la page des offres...")
            page.goto("https://ec-lyon.jobteaser.com/fr/job-offers", wait_until="commit")
            
            # On attend que l'interface de recherche soit là
            try:
                page.wait_for_selector('input[type="search"], .sk-SearchInput_input', timeout=20000)
                print("✅ [ROBOT] Interface des offres chargée.")
            except:
                print(f"⚠️ Interface non détectée, tentative de continuation... URL: {page.url}")

            # ÉTAPE 3 : Boucle de recherche organique
            for kw in keywords:
                print(f"--- 🔎 Recherche : {kw} ---")
                try:
                    # On cible la barre de recherche
                    search_input = page.locator('input[type="search"], #query, .sk-SearchInput_input').first
                    search_input.click()
                    
                    # On efface et on tape doucement
                    page.keyboard.press("Control+A")
                    page.keyboard.press("Backspace")
                    page.keyboard.type(kw, delay=random.randint(50, 120))
                    page.keyboard.press("Enter")
                    
                    # Attente de l'apparition des cartes (Sélecteur Skiller de ton HTML)
                    print("🤖 [ROBOT] Attente du rendu des offres...")
                    page.wait_for_selector('a[class*="sk-Card_main"]', timeout=15000)
                    time.sleep(3) # Laisse le JS finir l'affichage des titres

                    offers = page.locator('a[class*="sk-Card_main"]').all()
                    print(f"🎯 {len(offers)} offres détectées pour '{kw}'.")

                    for offer in offers:
                        try:
                            # Titre via la classe précise
                            title = offer.locator('h3[class*="JobAdCard_title"]').inner_text()
                            # Entreprise via data-testid
                            company = offer.locator('[data-testid="jobad-card-company-name"]').inner_text()
                            # Lien direct
                            href = offer.get_attribute('href')
                            
                            if title and company and href:
                                results.append({
                                    'title': title.strip(),
                                    'company': company.strip(),
                                    'location': 'Exclu JobTeaser (ENISE)',
                                    'job_url': f"https://ec-lyon.jobteaser.com{href}" if href.startswith('/') else href,
                                    'site': 'jobteaser'
                                })
                        except: continue
                except Exception as e:
                    print(f"⚠️ Pas de résultats ou blocage pour '{kw}'.")
                    continue

        except Exception as e:
            print(f"❌ Erreur critique Scraping : {e}")
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

        # A. SCRAPING PUBLIC (LinkedIn/Indeed via JobSpy)
        print(f"🔎 Scraping Public pour {email}...")
        for loc in prefs["villes"]:
            for kw in MOTS_CLES:
                try:
                    jobs = scrape_jobs(
                        site_name=["linkedin", "indeed"],
                        search_term=kw,
                        location=f"{loc}, France",
                        distance=prefs["dist"],
                        results_wanted=10,
                        hours_old=336,
                        country_indeed='france'
                    )
                    if not jobs.empty: 
                        all_results.append(jobs)
                        print(f"✅ {len(jobs)} offres publiques trouvées pour {kw} à {loc}")
                except Exception as e: 
                    print(f"⚠️ Erreur JobSpy ({kw}): {e}")
                    continue

        # B. SCRAPING PRIVÉ (JobTeaser)
        if JT_PASS:
            jt_data = scrape_jobteaser(email, JT_PASS, MOTS_CLES)
            if jt_data: 
                all_results.append(pd.DataFrame(jt_data))

        # C. MISE À JOUR FIREBASE
        if all_results:
            final_df = pd.concat(all_results).drop_duplicates(subset=['job_url'])
            final_df = final_df.astype(str)
            
            db.collection('jobs').document(email.lower()).set({
                'offers': final_df.to_dict(orient='records'),
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            print(f"✨ Terminé ! {len(final_df)} offres au total stockées pour {email}")
        else:
            print(f"❌ Aucune offre trouvée pour {email}")
