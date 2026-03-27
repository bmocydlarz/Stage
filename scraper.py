import pandas as pd
from jobspy import scrape_jobs
import firebase_admin
from firebase_admin import credentials, firestore
from playwright.sync_api import sync_playwright
import os, json, time

# --- 1. INITIALISATION FIREBASE ---
def init_firebase():
    if not firebase_admin._apps:
        # Récupération du secret depuis GitHub Actions
        service_account_info = json.loads(os.getenv('FIREBASE_SERVICE_ACCOUNT'))
        cred = credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(cred)
    return firestore.client()

# --- 2. FONCTION SCRAPING JOBTEASER ---
def scrape_jobteaser(email, password, keywords):
    results = []
    print(f"🔑 Tentative de connexion JobTeaser pour {email}...")
    
    with sync_playwright() as p:
        # On définit un "User Agent" pour ne pas être détecté comme un robot
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        try:
            login_url = "https://connect.jobteaser.com/?client_id=e500827d-07fc-4766-97b4-4f960a2835e7&entity_name=Ecole+Centrale+Lyon&organization_domain=ec-lyon&redirect_uri=https%3A%2F%2Fwww.jobteaser.com%2Fusers%2Fauth%2Fconnect%2Fcallback&response_type=code&ui_locales=fr"
            page.goto(login_url, wait_until="networkidle")

            # --- GESTION DES COOKIES ---
            # On cherche les boutons classiques "Tout accepter" ou "Accepter"
            try:
                # On attend 5 secondes max pour le bouton cookie
                cookie_button = page.locator('button:has-text("Tout accepter"), button:has-text("Accepter"), #CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll')
                if cookie_button.is_visible():
                    cookie_button.click()
                    print("🍪 Cookies acceptés")
            except:
                pass # Si pas de bandeau, on continue

            # --- CONNEXION ---
            page.fill('input[type="email"]', email)
            page.fill('input[type="password"]', password)
            
            # On clique et on attend que la navigation se fasse
            page.click('button[type="submit"]')
            
            # On attend qu'un élément de la barre de recherche apparaisse (preuve qu'on est loggé)
            # 'input' est très générique, on vise un sélecteur stable de JobTeaser
            page.wait_for_selector('nav, .jt-search-input, [data-testid="search-input"]', timeout=45000)
            print("✅ Connexion réussie, accès au tableau de bord.")

            # --- RECHERCHE ---
            # --- RECHERCHE ---
            for kw in keywords:
                search_url = f"https://www.jobteaser.com/fr/job-offers?query={kw.replace(' ', '+')}"
                
                # CHANGEMENT ICI : on attend seulement le chargement du DOM, pas le calme réseau
                page.goto(search_url, wait_until="domcontentloaded")
                
                # On attend spécifiquement qu'un article apparaisse
                try:
                    page.wait_for_selector('article', timeout=15000)
                except:
                    print(f"   ⚠️ Aucune offre affichée pour {kw}")
                    continue
                
                # Petit délai pour laisser le temps au JS de remplir les articles
                time.sleep(2) 
                
                offers = page.locator('article').all()
                for offer in offers:
                    try:
                        # Sélecteurs plus robustes (on prend le premier h2/h3 pour le titre)
                        title_el = offer.locator('h2, h3').first
                        company_el = offer.locator('p').first
                        link_el = offer.locator('a').first
                        
                        if title_el and company_el:
                            title = title_el.inner_text()
                            company = company_el.inner_text()
                            link = link_el.get_attribute('href')
                            full_link = f"https://www.jobteaser.com{link}" if link.startswith('/') else link
                            
                            results.append({
                                'title': title.strip(),
                                'company': company.strip(),
                                'location': 'JobTeaser (Centrale/ENISE)',
                                'job_url': full_link,
                                'site': 'jobteaser'
                            })
                    except: continue
                print(f"   🔎 {kw} : {len(results)} offres trouvées")

        except Exception as e:
            print(f"⚠️ Erreur JobTeaser : {e}")
        finally:
            browser.close()
    return results

# --- 3. EXECUTION PRINCIPALE ---
if __name__ == "__main__":
    db = init_firebase()
    
    # Configuration des utilisateurs
    # NOTE: L'email ici doit être celui utilisé pour JobTeaser
    USERS = {
        "baptiste.mocydlarz@etu-enise.ec-lyon.fr": {"villes": ["Saint-Étienne", "Lille"], "dist": 30}
    }

    MOTS_CLES = ["Stage Génie Mécanique", "Stage Conception CAO", "Stage Industrialisation", "Stage R&D"]
    JT_PASS = os.getenv('JOBTEASER_PASS')

    for email, prefs in USERS.items():
        all_results = []

        # A. Scraping JobSpy (LinkedIn/Indeed)
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

        # B. Scraping JobTeaser
        if JT_PASS:
            jt_jobs = scrape_jobteaser(email, JT_PASS, MOTS_CLES)
            if jt_jobs:
                all_results.append(pd.DataFrame(jt_jobs))

        # C. Envoi vers Firebase
        if all_results:
            final_df = pd.concat(all_results).drop_duplicates(subset=['job_url'])
            # Nettoyage pour Firebase
            final_df = final_df.astype(str)
            
            # On utilise l'email en minuscule comme ID de document
            db.collection('jobs').document(email.lower()).set({
                'offers': final_df.to_dict(orient='records'),
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            print(f"✨ Terminé ! {len(final_df)} offres stockées pour {email}")
