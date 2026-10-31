# Futbol Filtri — GitHub Pages versiyası

Bu qovluq Streamlit-dən asılı olmayan statik HTML/CSS/JavaScript versiyasıdır.

## GitHub Pages-də yayımlamaq
1. `https://github.com/zeosksoftwareecosystem/futbol` repozitoriyasını aç.
2. **Add file → Upload files** seç.
3. Bu qovluğun içindəki `index.html`, `style.css`, `app.js`, `README_AZ.md` fayllarını repozitoriyanın kök qovluğuna yüklə. `app.py` və `requirements.txt` fayllarını silmək lazım deyil.
4. **Commit changes** et.
5. **Settings → Pages** bölməsinə keç.
6. **Build and deployment → Deploy from a branch** seç; branch `main`, folder `/(root)` seç və Save et.
7. Yayımlandıqdan sonra sayt ünvanı adətən `https://zeosksoftwareecosystem.github.io/futbol/` olacaq.

## Vacib məhdudiyyət
GitHub Pages Python kodunu işə salmır. Bu versiya brauzerdə işləyir və oyunları ESPN-in açıq scoreboard API-sindən almağa çalışır. ESPN-də olan yarışlarla məhdudlaşır; əvvəlki Python tətbiqindəki bütün mənbələr, bütün çempionatlar və künc/kart statistikaları bu statik versiyaya avtomatik köçürülməyib. API-nin cavabı və CORS siyasəti dəyişərsə, məlumat yüklənməyə bilər. Faizlər yalnız API-dən əldə olunan tarixçə əsasında hesablanır.
