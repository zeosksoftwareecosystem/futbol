# Futbol Filtri — mobil veb tətbiq

Bu tətbiq telefonda Chrome/Safari ilə açılan Streamlit proqramıdır. Məlumatları Open Matchday GitHub repozitoriyasının arxivindən götürür və təxminən 6 saat keşdə saxlayır. “Məlumatları yenilə” düyməsi keşdən kənar təzə arxiv endirir.

## Pulsuz yerləşdirmə (Streamlit Community Cloud)

1. GitHub-da yeni repo yarat (məsələn, `futbol-filtri`).
2. Bu qovluqdakı `app.py` və `requirements.txt` fayllarını həmin repoya yüklə.
3. https://share.streamlit.io/ saytına daxil ol, GitHub ilə giriş et və **Create app** seç.
4. Repository, branch (`main`) və əsas fayl (`app.py`) seçib deploy et.
5. Tətbiq hazır olanda linki telefonda aç.

## Yalnız özün üçün şifrə

Streamlit Community Cloud-da tətbiqin **Settings → Secrets** bölməsinə bunu əlavə et:

```toml
APP_PASSWORD = "BURAYA_GUCLU_SIFRE_YAZ"
```

Save edib tətbiqi yenidən başladandan sonra şifrə soruşacaq. Secrets təyin edilməsə, tətbiq xəbərdarlıq göstərir və linki bilənlər aça bilər. Şifrəni GitHub koduna yazma.

## Filtrlər

- Hər komandanın son 2, 3, 4, 5, 6, 8 və ya 10 tamamlanmış oyunu
- BTTS, tam oyun 2.5/3.5/4.5 üst
- Birinci hissə 0.5/1.5 üst
- Künc və sarı vərəqə minimumları
- Tarix aralığı, nəticə cədvəli və CSV yükləmə

Mənbədə ofsayd sütunu yoxdur. Künc/kart və fasilə məlumatları bəzi matçlarda boş ola bilər. Tarixçə eyni yarışın nəticə faylı üzrə yoxlanılır. Pulsuz hostinqin işləmə, yaddaş və əlçatanlıq limitləri ola bilər.
