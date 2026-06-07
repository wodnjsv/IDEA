# Nemotron-Personas-Korea 데이터셋 구조 (확인 완료)

총 1M 레코드 × 7 페르소나 변주 = 7M 페르소나

## 26개 필드

### 페르소나 서사 (7개)
- professional_persona, sports_persona, arts_persona, travel_persona, culinary_persona, family_persona, persona

### 페르소나 속성 (6개)
- cultural_background, skills_and_expertise, skills_and_expertise_list, hobbies_and_interests, hobbies_and_interests_list, career_goals_and_ambitions

### 인구통계/지리 (12개)
- sex (2값), age (19-99), marital_status (4값), military_status (2값)
- family_type (39값), housing_type (6값), education_level (7값), bachelors_field (11값)
- occupation (2K+ 직업), district (252개 시·군·구), province (17개 광역), country

### 식별자
- uuid

## 0단계 활용 핵심 필드
- 층화 추출: age, province, sex
- 프롬프트 입력: persona, professional_persona, family_persona, cultural_background, age, sex, province, district, occupation, education_level, family_type
