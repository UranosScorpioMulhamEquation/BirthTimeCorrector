import streamlit as st
import swisseph as swe
import datetime
import pytz
from timezonefinder import TimezoneFinder
import geonamescache

# إعداد واجهة التطبيق
st.set_page_config(page_title="أداة تصحيح ساعة الميلاد بواقعة الزواج", layout="wide", page_icon="⏰")

# 1. تهيئة قاعدة بيانات الدول والمدن العالمية
@st.cache_data
def load_geo_data():
    gc = geonamescache.GeonamesCache()
    countries = gc.get_countries()
    cities = gc.get_cities()
    
    country_map = {c['name']: code for code, c in countries.items()}
    sorted_countries = sorted(list(country_map.keys()))
    
    cities_by_country = {}
    for c_code in country_map.values():
        c_cities = [city for city in cities.values() if city['countrycode'] == c_code]
        c_cities_sorted = sorted(c_cities, key=lambda x: x['population'], reverse=True)
        cities_by_country[c_code] = c_cities_sorted
        
    return gc, country_map, sorted_countries, cities_by_country

gc, country_map, country_list, cities_by_country = load_geo_data()
tf = TimezoneFinder()

# ثوابت فلكية
PLANETS = {
    'Sun': swe.SUN, 'Moon': swe.MOON, 'Mercury': swe.MERCURY, 
    'Venus': swe.VENUS, 'Mars': swe.MARS, 'Jupiter': swe.JUPITER, 
    'Saturn': swe.SATURN, 'Uranus': swe.URANUS, 'Neptune': swe.NEPTUNE, 
    'Pluto': swe.PLUTO, 'Rahu': swe.TRUE_NODE
}

ZODIAC_NAMES = [
    "الحمل", "الثور", "الجوزاء", "السرطان", 
    "الأسد", "العذراء", "الميزان", "العقرب", 
    "القوس", "الجدي", "الدلو", "الحوت"
]

def get_base_utc_offset(date_obj, lat, lon):
    """حساب الفارق الزمني القياسي للدولة من الخريطة الجغرافية بدون توقيت صيفي"""
    tz_str = tf.timezone_at(lng=lon, lat=lat) or "UTC"
    local_tz = pytz.timezone(tz_str)
    dt_unaware = datetime.datetime.combine(date_obj, datetime.time(12, 0))
    loc_dt = local_tz.localize(dt_unaware, is_dst=False)
    return loc_dt.utcoffset().total_seconds() / 3600.0

def find_exact_solar_return_utc(target_year, natal_sun_lon, birth_month, birth_day, utc_birth_dt):
    """حساب لحظة العودة الشمسية الدقيقة بالاعتماد المباشر على التوقيت العالمي UTC"""
    guess_utc = datetime.datetime(target_year, birth_month, birth_day, utc_birth_dt.hour, utc_birth_dt.minute, utc_birth_dt.second)
    jd_guess = swe.julday(guess_utc.year, guess_utc.month, guess_utc.day, guess_utc.hour + guess_utc.minute/60.0 + guess_utc.second/3600.0)
    
    for _ in range(20):
        sun_lon = swe.calc_ut(jd_guess, swe.SUN)[0][0]
        diff = (natal_sun_lon - sun_lon)
        if diff > 180: diff -= 360
        if diff < -180: diff += 360
        jd_guess += diff / 0.985647
        if abs(diff) < 0.000001:
            break
    return jd_guess

def get_house_of_planet(p_lon, cusps):
    for i in range(12):
        c1 = cusps[i]
        c2 = cusps[(i + 1) % 12]
        if c1 < c2:
            if c1 <= p_lon < c2: return i + 1
        else:
            if p_lon >= c1 or p_lon < c2: return i + 1
    return 1

def check_midpoint_activation(sr_planets, midpoint_lon):
    """تحقق من تفعيل الميد بوينت: الكوكب السنوي في نفس البرج وبفرق أقل من درجتين لكل الكواكب"""
    midpoint_sign = int(midpoint_lon / 30)
    activated_planets = []
    
    for p_name, p_data in sr_planets.items():
        p_lon = p_data['lon']
        p_sign = p_data['sign']
        
        if p_sign == midpoint_sign:
            diff = abs(p_lon - midpoint_lon)
            if diff < 2.0:
                deg_in_sign = p_lon % 30
                activated_planets.append(f"{p_name} في {deg_in_sign:.1f}° {ZODIAC_NAMES[p_sign]} [فرق: {diff:.1f}°]")
                
    return activated_planets

def is_before_cusp(p_lon, cusp_lon, orb=3): # تم التعديل إلى 3 درجات
    return ((cusp_lon - p_lon) % 360) <= orb

# --- واجهة المستخدم ---
st.title("🔍 أداة تصحيح ساعة الميلاد بواسطة واقعة الزواج")
st.caption("برمجة الفلكي و المبرمج الدكتور ملهم أحمد - دقة الأداة +/- 15 دقيقة عن توقيت الميلاد")
st.markdown("---")

st.sidebar.header("إعدادات البحث والتصحيح")
marriage_date = st.sidebar.date_input("تاريخ الزواج الفعلي المؤكد", value=datetime.date(2020, 1, 1), min_value=datetime.date(1960, 1, 1))

col1, col2, col3 = st.columns(3)

default_b_country_idx = country_list.index("Syria") if "Syria" in country_list else 0
default_sr_country_idx = country_list.index("United Arab Emirates") if "United Arab Emirates" in country_list else 0

with col1:
    st.markdown("### البيانات الشخصية")
    name = st.text_input("الاسم", "New Name")
    birth_date = st.date_input("تاريخ الميلاد", value=datetime.date(1990, 1, 1))
    expected_time = st.time_input("وقت الميلاد المتوقع", value=datetime.time(12, 0))
    st.info("سيتم فحص نطاق زمني تلقائي (نصف ساعة قبل ونصف ساعة بعد الوقت المتوقع).")

with col2:
    st.markdown("### مكان الميلاد")
    b_country_name = st.selectbox("دولة الميلاد", country_list, index=default_b_country_idx, key="b_country")
    b_c_code = country_map[b_country_name]
    b_city_objects = cities_by_country.get(b_c_code, [])
    b_city_names = [c['name'] for c in b_city_objects] if b_city_objects else [b_country_name]
    default_b_city_idx = b_city_names.index("Damascus") if "Damascus" in b_city_names else 0
    b_city_name = st.selectbox("مدينة الميلاد", b_city_names, index=default_b_city_idx, key="b_city")

with col3:
    st.markdown("### مكان الإقامة أثناء سنة الزواج")
    sr_country_name = st.selectbox("دولة السنوية", country_list, index=default_sr_country_idx, key="sr_country")
    sr_c_code = country_map[sr_country_name]
    sr_city_objects = cities_by_country.get(sr_c_code, [])
    sr_city_names = [c['name'] for c in sr_city_objects] if sr_city_objects else [sr_country_name]
    default_sr_city_idx = sr_city_names.index("Abu Dhabi") if "Abu Dhabi" in sr_city_names else 0
    sr_city_name = st.selectbox("مدينة السنوية", sr_city_names, index=default_sr_city_idx, key="sr_city")

run_rectification = st.button("بدء عملية تصحيح وقت الميلاد", type="primary")

if run_rectification:
    b_city_obj = next((c for c in b_city_objects if c['name'] == b_city_name), None)
    sr_city_obj = next((c for c in sr_city_objects if c['name'] == sr_city_name), None)
    
    b_lat, b_lon = (b_city_obj['latitude'], b_city_obj['longitude']) if b_city_obj else (35.1314, 36.7578)
    sr_lat, sr_lon = (sr_city_obj['latitude'], sr_city_obj['longitude']) if sr_city_obj else (24.4667, 54.3667)
        
    final_utc_offset = get_base_utc_offset(birth_date, b_lat, b_lon)
    st.info(f"**الفارق الزمني المعتمد للتطبيق (بدون توقيت صيفي):** UTC{'+' if final_utc_offset>=0 else ''}{final_utc_offset:g} ساعة")

    expected_dt = datetime.datetime.combine(birth_date, expected_time)
    start_dt = expected_dt - datetime.timedelta(minutes=30)
    end_dt = expected_dt + datetime.timedelta(minutes=30)
    
    time_step_seconds = 10 
    candidate_dts = []
    curr_dt = start_dt
    while curr_dt <= end_dt:
        candidate_dts.append(curr_dt)
        curr_dt += datetime.timedelta(seconds=time_step_seconds)
        
    matching_results = []
    progress_bar = st.progress(0.0)
    status_text = st.empty()
    
    marriage_year = marriage_date.year

    for idx, cand_dt in enumerate(candidate_dts):
        if idx % 100 == 0:
            progress_bar.progress((idx + 1) / len(candidate_dts))
            status_text.text(f"جاري الفحص... الوقت الحالي: {cand_dt.strftime('%H:%M:%S')}")
        
        utc_birth_dt = cand_dt - datetime.timedelta(hours=final_utc_offset)
        jd_birth = swe.julday(utc_birth_dt.year, utc_birth_dt.month, utc_birth_dt.day, utc_birth_dt.hour + utc_birth_dt.minute/60.0 + utc_birth_dt.second/3600.0)
        
        natal_sun = swe.calc_ut(jd_birth, swe.SUN)[0][0]
        natal_moon = swe.calc_ut(jd_birth, swe.MOON)[0][0]
        natal_cusps, _ = swe.houses(jd_birth, b_lat, b_lon, b'R')
        
        midpoint_lon = (natal_sun + natal_moon) / 2.0
        if abs(natal_sun - natal_moon) > 180:
            midpoint_lon = (midpoint_lon + 180) % 360
            
        jd_sr = find_exact_solar_return_utc(marriage_year, natal_sun, birth_date.month, birth_date.day, utc_birth_dt)
        sr_cusps, _ = swe.houses(jd_sr, sr_lat, sr_lon, b'R')
        sr_asc = sr_cusps[0]
        
        sr_planets = {}
        for p_name, p_id in PLANETS.items():
            lon = swe.calc_ut(jd_sr, p_id)[0][0]
            sr_planets[p_name] = {'lon': lon, 'sign': int(lon/30), 'deg_in_sign': lon%30, 'house': get_house_of_planet(lon, sr_cusps)}
            
        rahu_lon = sr_planets['Rahu']['lon']
        ketu_lon = (rahu_lon + 180) % 360
        sr_planets['Ketu'] = {
            'lon': ketu_lon,
            'sign': int(ketu_lon / 30),
            'deg_in_sign': ketu_lon % 30,
            'house': get_house_of_planet(ketu_lon, sr_cusps)
        }

        act_midpoint = check_midpoint_activation(sr_planets, midpoint_lon)
        if not act_midpoint:
            continue
        
        dallalat_count = 0
        details = []
        
        sr_asc_in_natal = get_house_of_planet(sr_asc, natal_cusps)
        if sr_asc_in_natal in [1, 4, 5, 7, 10]:
            dallalat_count += 1
            details.append(f"1. طالع العودة الشمسية يقع في **البيت {sr_asc_in_natal} الميلادي**")

        if sr_planets['Sun']['house'] in [1, 4, 5, 7, 10]:
            dallalat_count += 1
            details.append(f"2. الشمس السنوية في **البيت {sr_planets['Sun']['house']} السنوي**")
            
        if sr_planets['Moon']['house'] in [1, 4, 5, 7, 10]:
            dallalat_count += 1
            details.append(f"3. القمر السنوي في **البيت {sr_planets['Moon']['house']} السنوي**")

        planets_in_7th = [p_name for p_name, p_data in sr_planets.items() if p_data['house'] == 7]
        if len(planets_in_7th) >= 1:
            dallalat_count += 1
            details.append(f"4. تواجد كواكب بالبيت السابع السنوي ({', '.join(planets_in_7th)})")

        if len(planets_in_7th) >= 3:
            dallalat_count += 1
            details.append(f"5. هيمنة البيت السابع السنوي بـ ({len(planets_in_7th)}) كواكب")

        planets_in_5th = [p_name for p_name in ['Venus', 'Jupiter', 'Sun', 'Moon'] if sr_planets[p_name]['house'] == 5]
        if len(planets_in_5th) >= 1:
            dallalat_count += 1
            details.append(f"6. تواجد أدلة عاطفية في البيت 5 السنوي ({', '.join(planets_in_5th)})")

        if sr_planets['Venus']['house'] in [1, 4, 5, 7, 10] or sr_planets['Venus']['sign'] in [1, 3, 6, 9, 11]:
            dallalat_count += 1
            details.append(f"7. الزهرة في موقع قوي إما بالبيت {sr_planets['Venus']['house']} أو برج مستجيب")

        if sr_planets['Mars']['sign'] in [0, 9] or sr_planets['Mars']['house'] in [1, 4, 5, 7, 10]:
            dallalat_count += 1
            details.append(f"8. المريخ في موقعه الأصلي/شرفه أو بالبيت {sr_planets['Mars']['house']} السنوي")
             
        if sr_planets['Jupiter']['house'] in [1, 4, 5, 7, 10]:
            dallalat_count += 1
            details.append(f"9. المشتري في بيت سعيد/رئيسي (البيت {sr_planets['Jupiter']['house']})")

        target_planets = ['Uranus', 'Venus', 'Jupiter', 'Sun', 'Rahu', 'Ketu', 'Mars', 'Moon']
        target_cusps = [sr_cusps[0], sr_cusps[3], sr_cusps[4], sr_cusps[6], sr_cusps[9]]
        
        cusp_contacts = []
        for p_name in target_planets:
            p_lon = sr_planets[p_name]['lon']
            for cusp_idx, cusp in enumerate(target_cusps):
                if is_before_cusp(p_lon, cusp, orb=3): # استخدام الأورب 3 درجات
                    house_num = 1 if cusp_idx==0 else (4 if cusp_idx==1 else (5 if cusp_idx==2 else (7 if cusp_idx==3 else 10)))
                    cusp_contacts.append(f"{p_name} قبل وتد البيت {house_num}")
                    break
                    
        if cusp_contacts:
            dallalat_count += 1
            details.append(f"10. اتصال أدلة الزواج بأوتاد السنوية بـ 3 درجات فأقل: ({', '.join(cusp_contacts)})")

        # إظهار النتائج التي تفوق 4 دلالات
        if dallalat_count > 4:
            matching_results.append({
                "time": cand_dt.strftime("%H:%M:%S"),
                "natal_asc": f"{natal_cusps[0]%30:.1f}° {ZODIAC_NAMES[int(natal_cusps[0]/30)]}",
                "dallalat": dallalat_count,
                "midpoint_acts": act_midpoint,
                "details": details
            })

    progress_bar.progress(1.0)
    status_text.empty()

    matching_results.sort(key=lambda x: x['dallalat'], reverse=True)

    st.subheader(f"⏱️ النتيجة المقترحة لتصحيح وقت الميلاد لواقعة زواج بتاريخ {marriage_date.strftime('%Y-%m-%d')}:")
    
    if matching_results:
        best_match = matching_results[0]
        st.success("تم العثور على وقت الميلاد المقترح الذي يحقق أعلى عدد من دلالات الزواج وشرط الميد بوينت.")
        
        st.write(f"### ⏰ وقت الميلاد المقترح: **`{best_match['time']}`**")
        st.write(f"**عدد الدلالات المتحققة:** {best_match['dallalat']} من 10 (الحد الأدنى المطلوب: 5)")
        st.write(f"**طالع الميلاد عند هذا الوقت:** {best_match['natal_asc']}")
        
        st.markdown("#### 📌 الكواكب المفعلة للميد بوينت:")
        for act in best_match['midpoint_acts']:
            st.write(f"  * {act}")
            
        st.markdown("#### 📌 تفاصيل الدلالات السنوية المتحققة:")
        for d in best_match['details']:
            st.write(f"- {d}")
    else:
        st.warning("لم يتم العثور على أي وقت ميلاد ضمن النطاق المحدد يحقق تفعيل الميد بوينت وتجاوز 4 دلالات زواج على الأقل.")
