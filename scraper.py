import pandas as pd
from jobspy import scrape_jobs
import firebase_admin
from firebase_admin import credentials, firestore
from playwright.sync_api import sync_playwright
import os, json, time

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
    print(f"🤖 [ROBOT] Démarrage du module JobTeaser...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # On définit un User-Agent réaliste pour éviter d'être bloqué
        context = browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        try:
            # 1. Page de Login
            login_url = "https://connect.jobteaser.com/?client_id=e500827d-07fc-4766-97b4-4f960a2835e7&entity_name=Ecole+Centrale+Lyon&organization_domain=ec-lyon&redirect_uri=https%3A%2F%2Fwww.jobteaser.com%2Fusers%2Fauth%2Fconnect%2Fcallback&response_type=code&ui_locales=fr"
            print(f"🤖 [ROBOT] Connexion au portail Centrale Lyon...")
            page.goto(login_url, wait_until="domcontentloaded")
            
            # --- GESTION DES COOKIES ---
            time.sleep(2)
            try:
                page.click('button:has-text("Accepter"), button:has-text("OK"), [id*="cookie"] button', timeout=5000)
                print("🤖 [ROBOT] Cookies acceptés.")
            except: 
                pass

            # 2. Remplissage
            page.fill('input[type="email"]', email)
            page.fill('input[type="password"]', password)
            print(f"🤖 [ROBOT] Identifiants saisis. Envoi du formulaire...")
            
            # On utilise "Enter" pour valider plus sûrement qu'un clic sur bouton
            page.keyboard.press("Enter")
            
            # On attend d'être redirigé vers le domaine principal de JobTeaser
            page.wait_for_url("https://www.jobteaser.com/**", timeout=30000)
            print(f"🤖 [ROBOT] ✅ Connecté ! URL actuelle : {page.url}")

            # 4. Boucle de recherche sur le sous-domaine EC-LYON
            for kw in keywords:
                kw_encoded = kw.replace(' ', '+')
                # Utilisation du portail spécifique pour voir les offres école
                search_url = f"https://ec-lyon.jobteaser.com/fr/job-offers?query={kw_encoded}&q={kw_encoded}"
                
                print(f"🤖 [ROBOT] Recherche sur le portail école : {kw}")
                page.goto(search_url)
                
                # Attente que les offres (balises article) soient visibles
                try:
                    page.wait_for_selector('article', timeout=15000)
                    time.sleep(3) # Temps pour le chargement des données JS
                    
                    offers = page.locator('article').all()
                    count_kw = 0
                    for offer in offers:
                        try:
                            title = offer.locator('h2, h3').first.inner_text()
                            company = offer.locator('p').first.inner_text()
                            link = offer.locator('a').first.get_attribute('href')
                            
                            if title and company and link:
                                full_link = f"https://ec-lyon.jobteaser.com{link}" if link.startswith('/') else link
                                results.append({
                                    'title': title.strip(),
                                    'company': company.strip(),
                                    'location': 'JobTeaser (Centrale/ENISE)',
                                    'job_url': full_link,
                                    'site': 'jobteaser'
                                })
                                count_kw += 1
                        except: continue
                    print(f"🤖 [ROBOT] Found {count_kw} offres pour '{kw}'")
                except:
                    print(f"🤖 [ROBOT] ⚠️ Aucune offre visible pour '{kw}' sur le portail école.")

        except Exception as e:
            print(f"🤖 [ROBOT] ❌ ERREUR : {e}")
            print(f"🤖 [ROBOT] Page d'erreur : {page.url}")
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

        # A. Scraping Public (LinkedIn/Indeed)
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
                    if not jobs.empty:
                        all_results.append(jobs)
                except: continue

        # B. Scraping JobTeaser (Portail École)
        if JT_PASS:
            jt_jobs = scrape_jobteaser(email, JT_PASS, MOTS_CLES)
            if jt_jobs:
                all_results.append(pd.DataFrame(jt_jobs))

        # C. Fusion et Envoi vers Firebase
        if all_results:
            # Fusion de tous les DataFrames (Public + JobTeaser)
            final_df = pd.concat(all_results).drop_duplicates(subset=['job_url'])
            final_df = final_df.astype(str)
            
            db.collection('jobs').document(email.lower()).set({
                'offers': final_df.to_dict(orient='records'),
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            print(f"✨ Terminé ! {len(final_df)} offres au total stockées pour {email}")
