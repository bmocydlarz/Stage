import pandas as pd
from jobspy import scrape_jobs
import datetime

def generate_html(df):
    # On trie par date pour avoir les plus récents en haut
    df = df.sort_values(by='date_posted', ascending=False)
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Ma Veille Stages Méca 🛠️</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-100 p-4">
        <div class="max-w-3xl mx-auto">
            <header class="mb-8">
                <h1 class="text-3xl font-bold text-blue-900">🎯 Mes Offres de Stage</h1>
                <p class="text-gray-600">Dernière mise à jour : {datetime.datetime.now().strftime('%d/%m/%Y à %H:%M')}</p>
                <div class="flex gap-2 mt-2">
                    <span class="bg-blue-100 text-blue-800 text-xs font-semibold px-2.5 py-0.5 rounded">Saint-Étienne (25km)</span>
                    <span class="bg-green-100 text-green-800 text-xs font-semibold px-2.5 py-0.5 rounded">Quesnoy-sur-Deûle (25km)</span>
                </div>
            </header>
            <div class="space-y-4">
    """
    
    if df.empty:
        html_content += "<p class='text-center py-10 text-gray-500'>Aucune nouvelle offre trouvée aujourd'hui. 😴</p>"
    else:
        for _, row in df.iterrows():
            # Formatage de la date si disponible
            date_str = row['date_posted'] if pd.notnull(row['date_posted']) else "Récent"
            
            html_content += f"""
            <div class="bg-white p-5 rounded-xl shadow-sm border border-gray-200 hover:shadow-md transition">
                <div class="flex justify-between items-start">
                    <h2 class="text-xl font-bold text-gray-800 leading-tight">{row['title']}</h2>
                    <span class="text-xs font-medium text-gray-400">{date_str}</span>
                </div>
                <p class="text-blue-700 font-semibold mt-1 text-lg">{row['company']}</p>
                <p class="text-gray-600 flex items-center mt-1 italic">
                    📍 {row['location']}
                </p>
                <div class="mt-4 flex items-center justify-between">
                    <span class="text-sm font-medium px-2 py-1 bg-gray-100 rounded text-gray-600">Source : {row['site']}</span>
                    <a href="{row['job_url']}" target="_blank" 
                       class="bg-blue-600 text-white px-5 py-2 rounded-lg font-bold hover:bg-blue-800 transition">
                       Postuler
                    </a>
                </div>
            </div>
            """
    
    html_content += "</div><footer class='mt-10 text-center text-gray-400 text-sm'>Fin de la liste</footer></div></body></html>"
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

# --- CONFIGURATION DES RECHERCHES ---
recherches = [
    "Assistant Ingénieur Génie Mécanique",
    "Stage Conception Mécanique",
    "Stagiaire Ingénieur Mécanique",
    "Stage Maintenance Industrielle"
]

villes = [
    "Saint-Étienne, France",
    "Quesnoy-sur-Deûle, France"
]

all_jobs_list = []

print("🔎 Début de la multi-recherche...")

for ville in villes:
    for poste in recherches:
        print(f"📡 Recherche de '{poste}' à {ville}...")
        try:
            jobs = scrape_jobs(
                site_name=["linkedin", "indeed"],
                search_term=poste,
                location=ville,
                distance=15, # Environ 25km
                results_wanted=10,
                hours_old=168, # On regarde sur les 7 derniers jours
                country_indeed='france',
            )
            if not jobs.empty:
                all_jobs_list.append(jobs)
        except Exception as e:
            print(f"⚠️ Erreur sur {poste} à {ville}: {e}")

# Fusion et nettoyage des doublons
if all_jobs_list:
    final_df = pd.concat(all_jobs_list).drop_duplicates(subset=['job_url'])
    # Optionnel : On peut filtrer ici pour "septembre" ou "4 mois" dans la description
    # final_df = final_df[final_df['description'].str.contains("septembre|4 mois", case=False, na=False)]
    
    generate_html(final_df)
    print(f"✅ Terminé : {len(final_df)} offres uniques trouvées.")
else:
    generate_html(pd.DataFrame())
    print("❌ Aucun job trouvé.")
