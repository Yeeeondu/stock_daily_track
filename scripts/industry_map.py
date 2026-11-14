"""업종 매핑: 미국(GICS)·일본(東証33業種)을 공통 대분류(한글)로 맞춘다.
대분류는 GICS 11개 섹터를 기준으로 하고, 세부는 각 시장의 기존 업종명을 한글로 옮긴 것.
원하는 대로 자유롭게 고쳐 쓰면 된다. 매핑에 없는 값은 원문 그대로 표시된다."""

GICS_SECTOR = {
    "Energy": "에너지",
    "Materials": "소재",
    "Industrials": "산업재",
    "Consumer Discretionary": "경기소비재",
    "Consumer Staples": "필수소비재",
    "Health Care": "헬스케어",
    "Financials": "금융",
    "Information Technology": "IT",
    "Communication Services": "커뮤니케이션",
    "Utilities": "유틸리티",
    "Real Estate": "부동산",
}

GICS_SUB = {
    # 에너지
    "Oil & Gas Drilling": "석유·가스 시추", "Oil & Gas Equipment & Services": "유전 장비·서비스",
    "Integrated Oil & Gas": "종합 석유", "Oil & Gas Exploration & Production": "석유·가스 탐사·생산",
    "Oil & Gas Refining & Marketing": "정유", "Oil & Gas Storage & Transportation": "석유·가스 저장·운송",
    "Coal & Consumable Fuels": "석탄·연료",
    # 소재
    "Commodity Chemicals": "범용화학", "Diversified Chemicals": "종합화학",
    "Fertilizers & Agricultural Chemicals": "비료·농화학", "Industrial Gases": "산업용 가스",
    "Specialty Chemicals": "특수화학", "Construction Materials": "건자재",
    "Metal, Glass & Plastic Containers": "용기", "Paper & Plastic Packaging Products & Materials": "포장재",
    "Aluminum": "알루미늄", "Diversified Metals & Mining": "금속·광업", "Copper": "구리", "Gold": "금",
    "Precious Metals & Minerals": "귀금속", "Silver": "은", "Steel": "철강",
    "Forest Products": "임산물", "Paper Products": "제지",
    # 산업재
    "Aerospace & Defense": "항공우주·방산", "Building Products": "건축자재",
    "Construction & Engineering": "건설·엔지니어링", "Electrical Components & Equipment": "전기장비",
    "Heavy Electrical Equipment": "중전기", "Industrial Conglomerates": "산업 복합기업",
    "Construction Machinery & Heavy Transportation Equipment": "건설기계·중장비",
    "Agricultural & Farm Machinery": "농기계", "Industrial Machinery & Supplies & Components": "산업기계",
    "Trading Companies & Distributors": "상사·유통", "Commercial Printing": "상업인쇄",
    "Environmental & Facilities Services": "환경·시설 서비스", "Office Services & Supplies": "사무 서비스",
    "Diversified Support Services": "지원 서비스", "Security & Alarm Services": "보안 서비스",
    "Human Resource & Employment Services": "인력 서비스", "Research & Consulting Services": "리서치·컨설팅",
    "Data Processing & Outsourced Services": "데이터 처리·아웃소싱", "Air Freight & Logistics": "항공화물·물류",
    "Passenger Airlines": "항공사", "Marine Transportation": "해운", "Rail Transportation": "철도",
    "Cargo Ground Transportation": "화물 육운", "Passenger Ground Transportation": "여객 육운",
    "Airport Services": "공항 서비스", "Highways & Railtracks": "도로·철도 인프라", "Marine Ports & Services": "항만",
    # 경기소비재
    "Automotive Parts & Equipment": "자동차 부품", "Tires & Rubber": "타이어",
    "Automobile Manufacturers": "자동차", "Motorcycle Manufacturers": "이륜차",
    "Consumer Electronics": "가전", "Home Furnishings": "가구", "Homebuilding": "주택건설",
    "Household Appliances": "가전제품", "Housewares & Specialties": "생활용품", "Leisure Products": "레저용품",
    "Apparel, Accessories & Luxury Goods": "의류·명품", "Footwear": "신발", "Textiles": "섬유",
    "Casinos & Gaming": "카지노", "Hotels, Resorts & Cruise Lines": "호텔·크루즈", "Leisure Facilities": "레저시설",
    "Restaurants": "외식", "Education Services": "교육", "Specialized Consumer Services": "소비자 서비스",
    "Distributors": "유통", "Broadline Retail": "종합 소매", "Apparel Retail": "의류 소매",
    "Computer & Electronics Retail": "전자제품 소매", "Home Improvement Retail": "주택개량 소매",
    "Other Specialty Retail": "전문 소매", "Automotive Retail": "자동차 소매", "Homefurnishing Retail": "가구 소매",
    # 필수소비재
    "Drug Retail": "드럭스토어", "Food Distributors": "식품 유통", "Food Retail": "식품 소매",
    "Consumer Staples Merchandise Retail": "필수품 소매", "Brewers": "맥주", "Distillers & Vintners": "주류",
    "Soft Drinks & Non-alcoholic Beverages": "음료", "Agricultural Products & Services": "농산물",
    "Packaged Foods & Meats": "가공식품", "Tobacco": "담배", "Household Products": "생활용품",
    "Personal Care Products": "화장품·개인용품",
    # 헬스케어
    "Health Care Equipment": "의료기기", "Health Care Supplies": "의료용품",
    "Health Care Distributors": "의약품 유통", "Health Care Services": "의료 서비스",
    "Health Care Facilities": "의료시설", "Managed Health Care": "건강보험",
    "Health Care Technology": "헬스케어 IT", "Biotechnology": "바이오", "Pharmaceuticals": "제약",
    "Life Sciences Tools & Services": "생명과학 도구",
    # 금융
    "Diversified Banks": "대형 은행", "Regional Banks": "지역 은행",
    "Diversified Financial Services": "종합 금융", "Multi-Sector Holdings": "복합 지주",
    "Specialized Finance": "특수 금융", "Commercial & Residential Mortgage Finance": "모기지 금융",
    "Transaction & Payment Processing Services": "결제 서비스", "Consumer Finance": "소비자 금융",
    "Asset Management & Custody Banks": "자산운용", "Investment Banking & Brokerage": "증권·IB",
    "Diversified Capital Markets": "자본시장", "Financial Exchanges & Data": "거래소·금융데이터",
    "Mortgage REITs": "모기지 리츠", "Insurance Brokers": "보험중개", "Life & Health Insurance": "생명보험",
    "Multi-line Insurance": "종합보험", "Property & Casualty Insurance": "손해보험", "Reinsurance": "재보험",
    # IT
    "IT Consulting & Other Services": "IT 컨설팅", "Internet Services & Infrastructure": "인터넷 인프라",
    "Application Software": "응용 소프트웨어", "Systems Software": "시스템 소프트웨어",
    "Communications Equipment": "통신장비", "Technology Hardware, Storage & Peripherals": "하드웨어·저장장치",
    "Electronic Equipment & Instruments": "전자장비·계측기", "Electronic Components": "전자부품",
    "Electronic Manufacturing Services": "전자 위탁생산", "Technology Distributors": "IT 유통",
    "Semiconductor Materials & Equipment": "반도체 장비·소재", "Semiconductors": "반도체",
    # 커뮤니케이션
    "Alternative Carriers": "대체 통신사", "Integrated Telecommunication Services": "통신",
    "Wireless Telecommunication Services": "무선통신", "Advertising": "광고", "Broadcasting": "방송",
    "Cable & Satellite": "케이블·위성", "Publishing": "출판", "Movies & Entertainment": "영화·엔터",
    "Interactive Home Entertainment": "게임", "Interactive Media & Services": "인터넷 플랫폼",
    # 유틸리티
    "Electric Utilities": "전력", "Gas Utilities": "가스", "Multi-Utilities": "복합 유틸리티",
    "Water Utilities": "수도", "Independent Power Producers & Energy Traders": "독립 발전",
    "Renewable Electricity": "재생에너지",
    # 부동산
    "Diversified REITs": "복합 리츠", "Industrial REITs": "물류 리츠", "Hotel & Resort REITs": "호텔 리츠",
    "Office REITs": "오피스 리츠", "Health Care REITs": "헬스케어 리츠",
    "Multi-Family Residential REITs": "아파트 리츠", "Single-Family Residential REITs": "단독주택 리츠",
    "Retail REITs": "리테일 리츠", "Other Specialized REITs": "특수 리츠", "Self-Storage REITs": "창고 리츠",
    "Telecom Tower REITs": "통신탑 리츠", "Timber REITs": "임업 리츠", "Data Center REITs": "데이터센터 리츠",
    "Real Estate Services": "부동산 서비스", "Real Estate Development": "부동산 개발",
    "Real Estate Operating Companies": "부동산 운영", "Diversified Real Estate Activities": "종합 부동산",
}

# 東証33業種 → (공통 대분류, 세부)
JP33 = {
    "水産・農林業": ("필수소비재", "수산·농림"),
    "鉱業": ("에너지", "광업"),
    "建設業": ("산업재", "건설"),
    "食料品": ("필수소비재", "식료품"),
    "繊維製品": ("경기소비재", "섬유"),
    "パルプ・紙": ("소재", "펄프·종이"),
    "化学": ("소재", "화학"),
    "医薬品": ("헬스케어", "제약"),
    "石油・石炭製品": ("에너지", "석유·석탄"),
    "ゴム製品": ("소재", "고무"),
    "ガラス・土石製品": ("소재", "유리·요업"),
    "鉄鋼": ("소재", "철강"),
    "非鉄金属": ("소재", "비철금속"),
    "金属製品": ("소재", "금속제품"),
    "機械": ("산업재", "기계"),
    "電気機器": ("IT", "전기기기"),
    "輸送用機器": ("경기소비재", "수송용기기"),
    "精密機器": ("IT", "정밀기기"),
    "その他製品": ("경기소비재", "기타제품"),
    "電気・ガス業": ("유틸리티", "전기·가스"),
    "陸運業": ("산업재", "육운"),
    "海運業": ("산업재", "해운"),
    "空運業": ("산업재", "항공"),
    "倉庫・運輸関連業": ("산업재", "창고·운수"),
    "情報・通信業": ("커뮤니케이션", "정보·통신"),
    "卸売業": ("산업재", "도매·상사"),
    "小売業": ("경기소비재", "소매"),
    "銀行業": ("금융", "은행"),
    "証券、商品先物取引業": ("금융", "증권"),
    "保険業": ("금융", "보험"),
    "その他金融業": ("금융", "기타금융"),
    "不動産業": ("부동산", "부동산"),
    "サービス業": ("산업재", "서비스"),
}


def jp_category(s33: str):
    s = (s33 or "").strip()
    if s in JP33:
        return JP33[s]
    norm = s.replace("、", "").replace("，", "").replace(",", "")
    for k, v in JP33.items():
        if k.replace("、", "") == norm:
            return v
    return ("기타", s or "기타")


def us_category(sector: str, sub: str):
    sec = GICS_SECTOR.get((sector or "").strip(), (sector or "기타").strip())
    return sec, GICS_SUB.get((sub or "").strip(), (sub or "").strip() or sec)
