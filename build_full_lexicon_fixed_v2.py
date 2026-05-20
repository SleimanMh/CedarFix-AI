import csv, re

rows = []

# Schema: arabic_script, english, sector, issue_type, category,
#         v1..v6, tiers (A/B/C per variant), normalization (canonical Arabic), usage_note
# tier A = most natural Lebanese Arabizi, B = common alternate, C = rare/regional/abbreviated

def w(ar, en, sec, iss, cat, v1, v2='', v3='', v4='', v5='', v6='', tiers='', norm='', note=''):
    rows.append([ar, en, sec, iss, cat, v1, v2, v3, v4, v5, v6, tiers, norm, note])

# ══════════════════════════════════════════════════════════════
# ROADS — NOUNS
# ══════════════════════════════════════════════════════════════
w('حفرة','pothole / hole in road','ROADS','POTHOLE','noun_infra',
  '7ofra','7afra','hofra','7ofrit','7afrit','hufra',
  'A/A/B/B/C/C','حفرة',
  '7=ح always; hofra plain-h widely accepted; hufra C-tier (wrong char but seen); 7ofrit/7afrit diminutives')
w('جورة','pit / hole — Beiruti variant','ROADS','POTHOLE','noun_infra',
  'jora','joura','joora','jorit','joret','jwara',
  'A/A/B/B/C/C','جورة',
  'Entirely different root from حفرة; no ع/ح/خ/ق so no markers needed; Beiruti street speech')
w('حفر (plural)','potholes / holes (plural)','ROADS','POTHOLE','noun_infra',
  '7afarat','7ofar','hfar','7ufar','jourat','jowarat',
  'A/B/B/C/A/B','حفرات',
  '7=ح in plural forms; jourat = Beiruti plural of jora')
w('طريق','road','ROADS','ALL','noun_infra',
  'tari2','tare2','tari\'','triq','tare\'','tari22',
  'A/A/B/B/C/C','طريق',
  'tari2 overwhelmingly most common; triq North Lebanon variant; 2=ق')
w('شارع','street','ROADS','ALL','noun_infra',
  'share3','shar3','shara3','shari3','sheri3','share33',
  'A/A/B/B/C/C','شارع',
  '3=ع required; share3 standard; shari3/sheri3 more MSA-influenced')
w('طريق سريع','highway / motorway','ROADS','ALL','noun_infra',
  'otostrad','l otostrad','autostrad','tari2 sari3','autoroute','l fouye',
  'A/A/B/B/B/B','طريق سريع / أوتوستراد',
  'otostrad (Italian loanword) most common; l fouye colloquial for highway; autoroute French')
w('دوار','roundabout','ROADS','ALL','noun_infra',
  'dawwar','dawar','dawer','dawwara','l dawwar','dawwer',
  'A/A/B/C/A/C','دوار',
  'dawwar most natural; no special markers in this root')
w('منعطف','bend / curve in road','ROADS','ALL','noun_infra',
  'mona3taf','mna3taf','man3ataf','3al mna3taf','mon3ataf','3al mona3taf',
  'A/B/C/A/C/A','منعطف',
  '3=ع required; mona3taf most natural')
w('رصيف','sidewalk / pavement','ROADS','BROKEN_SIDEWALK','noun_infra',
  'rasif','rasife','rsayef','rsayfet','rssif','rseef',
  'A/A/B/B/C/C','رصيف',
  'rsayef natural plural; rsayfet construct-state plural')
w('بردورة','curb','ROADS','BROKEN_SIDEWALK','noun_infra',
  'bardore','bardoura','bardour','l bardore','burdure','bordure',
  'A/A/B/A/C/B','بردورة',
  'French loanword (bordure); bardore most natural Lebanese pronunciation')
w('بلاط','paving tiles / floor tiles','ROADS','BROKEN_SIDEWALK','noun_infra',
  'balat','blat','balet','balata','blayt','balt',
  'A/B/B/C/C/C','بلاط',
  'balat most common; balata = one tile; no Arabizi markers in this root')
w('غطاء بئر','manhole cover','ROADS','MISSING_MANHOLE','noun_infra',
  'ghata biar','ghata l biar','ghata l biyar','ghato','ghatit l biar','ghata mafqoud',
  'A/A/A/C/B/A','غطاء بئر',
  'ghata biar most natural; ghata mafqoud = cover is missing (descriptive)')
w('بئر / بيار','manhole / well','ROADS','MISSING_MANHOLE','noun_infra',
  'biar','biyar','bi2ar','biyara','byar','byarat',
  'A/A/B/B/C/B','بئر / بيار',
  '2=ق in bi2ar; biar most Lebanese; byarat = manholes plural')
w('مطب','speed bump','ROADS','ROAD_DAMAGE','noun_infra',
  'matab','matabb','mtab','l matab','matabeat','l matabeat',
  'A/A/B/A/B/A','مطب',
  'matab standard Lebanese; matabeat = speed bumps plural')
w('كاسر سرعة','speed breaker (descriptive)','ROADS','ROAD_DAMAGE','noun_infra',
  'kaser sur3a','kasret sur3a','kasir sor3a','mukab3','kashir sur3a','',
  'A/B/C/C/C','كاسر سرعة',
  '3=ع in sur3a/sor3a; mukab3 older slang')
w('جسر / كوبري','bridge / overpass','ROADS','ROAD_COLLAPSE','noun_infra',
  'jisr','koubri','kobri','jesr','l jisr','l koubri',
  'A/A/A/B/A/A','جسر / كوبري',
  'jisr Arabic; koubri most Beiruti colloquial; both very common')
w('نفق','tunnel','ROADS','ROAD_BLOCKED','noun_infra',
  'nafa2','nafa2a','nafeq','l nafa2','nfaq','nafeq ta7t l ard',
  'A/B/B/A/C/B','نفق',
  '2=ق; nafa2 most natural Lebanese')
w('حاجز','barrier / checkpoint','ROADS','ROAD_BLOCKED','noun_infra',
  '7ajez','7awajez','7ajiz','7ajez 7adid','7ajez kharsoune','barricade',
  'A/B/B/B/B/B','حاجز',
  '7=ح required; 7awajez = barriers plural; kharsoune = concrete barrier')
w('خرسانة','concrete','ROADS','ALL','noun_infra',
  'kharsoune','5arsoune','kharssoun','beton','bton','béton',
  'A/B/B/A/B/B','خرسانة',
  '5=خ in 5arsoune preferred; beton French loanword very common')
w('علامة طريق','road marking / line','ROADS','ALL','noun_infra',
  '5outet arda','5outout tari2','5outet bayde','khoutout','l 5outet','dye tari2',
  'A/A/A/B/B/C','خطوط طريق',
  '5=خ in 5outout; 5outet arda = white lane marking')
w('إشارة ضوئية','traffic light','ROADS','ROAD_BLOCKED','noun_infra',
  'feu','l feu','feu rouge','isharet dawiye','trafico','ishara',
  'A/A/A/B/B/B','إشارة ضوئية',
  'feu French loanword overwhelmingly dominant in Lebanon; feu rouge = red light')
w('لافتة','road sign / billboard sign','ROADS','ALL','noun_infra',
  'lafta','lafite','lawhat','l lafta','lafta sakat','lifte',
  'A/A/B/A/A/B','لافتة',
  'lafta most common Lebanese; sakat = fell down; lawhat more MSA')
w('تحويلة','detour','ROADS','ROAD_BLOCKED','noun_infra',
  'ta7wile','t7wile','msar bedil','ta7wili','ta7woleh','via bedil',
  'A/B/A/A/C/C','تحويلة',
  '7=ح; msar bedil = alternative route; ta7wile most natural')
w('زحمة','traffic jam / congestion','ROADS','ROAD_BLOCKED','noun_infra',
  'za7me','z7me','za7meh','za7ma','za7me ktir','za7mit seer',
  'A/B/A/C/A/A','زحمة',
  '7=ح in za7me; za7mit seer = traffic congestion; z7me contracted')
w('أعمال / شغلة','construction works','ROADS','ROAD_BLOCKED','noun_infra',
  'she3el','shi3el','ashghal','she3el tari2','fi she3el','a3mel tari2',
  'A/A/B/A/A/B','أعمال',
  '3=ع in she3el and ashghal; she3el most Lebanese; a3mel = works')
w('حفر / خندق','excavation / trench','ROADS','ROAD_BLOCKED','noun_infra',
  '7afr','5ande2','7afrit','5nde2','7ofra 5andou2','she3el 7afr',
  'A/A/B/B/B/A','حفر / خندق',
  '7=ح in 7afr/7afrit; 5=خ in 5ande2')
w('جرافة','bulldozer / excavator','ROADS','ROAD_BLOCKED','noun_infra',
  'jrafe','jrafi','7affar','7affare','buldozer','caterpillar',
  'A/B/A/A/B/B','جرافة / حفارة',
  '7=ح in 7affar; buldozer/caterpillar English loanwords common in Lebanon')
w('عمود إنارة','light pole / street lamp pole','ROADS','ALL','noun_infra',
  '3amoud nour','3amoud ishara','3amoud kahraba','3amoud','poteau','3amoud l share3',
  'A/A/A/A/B/A','عمود إنارة',
  '3=ع required; poteau French loanword also used')
w('ممر مشاة','pedestrian crossing','ROADS','ALL','noun_infra',
  'mammar msheh','mammar mshayye','zebra','passage piéton','5outout zebra','mammar',
  'A/A/A/B/B/A','ممر مشاة',
  'zebra most Beiruti slang for pedestrian crossing (from French/English)')
w('موقف سيارات','parking lot / space','ROADS','ALL','noun_infra',
  'maw2ef','maw2af','parking','l parking','maw2ef sayyara','parkinge',
  'A/B/A/A/A/B','موقف سيارات',
  '2=ق in maw2ef; parking English loanword dominant in Lebanese')
w('شجرة ساقطة','fallen tree','ROADS','ROAD_BLOCKED','noun_infra',
  'shajar seket','shajre sak3a','shajar 3al tari2','shajara saktet','shajar nkassar','',
  'A/A/A/A/B','شجرة ساقطة',
  '3=ع in 3al; seket/saktet = fell; no special markers in shajar')
w('صخرة / انزلاق تربة','fallen rock / landslide','ROADS','ROAD_BLOCKED','noun_infra',
  'sa5ra saktet','sa5ra 3al tari2','nzela2 turbe','n7iyaz ard','sa5ra nkassar','tasatte7',
  'A/A/B/B/B/C','صخرة / انزلاق تربة',
  '5=خ in sa5ra; 3=ع in 3al; nzela2 = slide; n7iyaz = subsidence')
w('هبوط أرضي','ground subsidence / sinkhole','ROADS','ROAD_COLLAPSE','noun_infra',
  'hobout ardi','hobout l ard','l ard nbset','sinkhole','l tari2 nbesat','tari2 2nhajar',
  'A/A/A/B/A/B','هبوط أرضي',
  '2=ق in 2nhajar; hobout = sinking; sinkhole English loanword also used')
w('تشقق','crack (noun)','ROADS','ROAD_CRACK','noun_infra',
  'tashaddo2at','tasha22o2at','shi22','tshaqqa2','tashroomaat','tshakko2',
  'A/B/B/C/C/B','تشقق / تشققات',
  '2=ق throughout; tashaddo2at most natural plural in Lebanese')
w('إسفلت / زفت','asphalt','ROADS','ALL','noun_infra',
  'asphalt','asphelt','asfalt','zeft','l asphalt','zft',
  'A/B/C/A/A/C','إسفلت',
  'asphalt borrowed English dominant; zeft Lebanese slang (also = terrible — context matters)')
w('درع / حاجز معدني','guardrail / metal barrier','ROADS','ALL','noun_infra',
  '7ajez 7adid','dara3 ma3dani','garde-corps','glissière','7adid 7ayye','7ajez lohoum',
  'A/B/B/B/B/C','درع معدني / حاجز حديدي',
  '7=ح twice; garde-corps/glissière French terms; lohoum = metal sheets (slang)')
w('خط سير','lane marking / traffic lane','ROADS','ALL','noun_infra',
  '5att seer','5att l seer','7aret l seer','7ara seer','voie','5outet seer',
  'A/A/A/A/B/B','خط سير',
  '5=خ in 5att; 7=ح in 7aret; voie French loanword')
w('مسار دراجات','bike lane','ROADS','ALL','noun_infra',
  'msar darrajat','msar bsikleta','piste cyclable','msar l bykes','bykes lane','',
  'A/A/B/B/C','مسار دراجات',
  'piste cyclable French; bykes/bikes English loanword very common in Beirut')
w('إشارة تحذير','warning sign','ROADS','ALL','noun_infra',
  'isharet ta7dir','isharit ta7dir','ishara ta7zir','paneau 5atar','paneau','panel',
  'A/B/C/B/B/B','إشارة تحذير',
  '7=ح in ta7dir; paneau French loanword (panneau) very common in Lebanon')
w('كتل خرسانية','concrete blocks (jersey barriers)','ROADS','ROAD_BLOCKED','noun_infra',
  'ketal kharsoune','l ketal','block kharsoune','jersey barrier','blokaat','blok',
  'A/A/A/B/B/B','كتل خرسانية',
  'ketal kharsoune most natural; blokaat = blocks (plural English loanword)')
w('حادث سير','traffic accident','ROADS','ALL','noun_infra',
  '7adit seer','7adit sayir','7adit tari2','7adet seer','accident','7adase seer',
  'A/A/B/B/B/B','حادث سير',
  '7=ح throughout; 7adit seer most common; accident French loanword also used')
w('تلوث هواء','air pollution / dust (from works)','ROADS','ALL','noun_infra',
  'trab w ghbar','ghbar ktir','ghbar men she3el','trab 3am yiti3','trab wajib','',
  'A/A/A/A/B','تلوث هواء / غبار',
  '3=ع in 3am; trab = dust/soil; ghbar = dust cloud')

# ══════════════════════════════════════════════════════════════
# ROADS — VERBS
# ══════════════════════════════════════════════════════════════
w('انهار / انكسر','collapsed / broke','ROADS','ROAD_COLLAPSE','verb',
  'nkassar','nhajar','nhaar','n7ajar','2nhajar','ta7',
  'A/B/B/B/C/B','انكسر / انهار',
  'nkassar most natural; nhajar = crumbled; ta7 = fell; 7=ح in n7ajar')
w('تشقق','cracked (verb)','ROADS','ROAD_CRACK','verb',
  'tsha22a2','tsha2a2','nshe2','tshe22','metshe22a2','sha22',
  'A/B/C/C/B/C','تشقق',
  '2=ق throughout; tsha22a2 most natural verb form')
w('انسفلت / رُمِّم','was paved / was repaired','ROADS','ALL','verb',
  'yisfelt','sfaltou','tarmamo','ytrammam','ramamo','3am yisfelt',
  'A/A/A/B/A/A','أُسفلت / رُمِّم',
  '3=ع in 3am; yisfelt most natural for paving; tarmamo = was repaired')
w('احتاج إصلاح','needs repair (state)','ROADS','ALL','verb',
  'me7teje tarmim','me7taj tarmim','bi 7ajit tarmim','lazmo yisla7','','',
  'A/A/A/A','يحتاج إصلاح',
  '7=ح in 7ajit; tarmim = repair/maintenance')
w('حوّل المرور','diverted traffic','ROADS','ROAD_BLOCKED','verb',
  '7awwalo l seer','3amelo ta7wile','ta7wile sal3a','7awwalo l tari2','','',
  'A/A/A/A','حوّل المرور',
  '7=ح twice; 3=ع in 3amelo')
w('سقط / وقع','fell / dropped','ROADS','ROAD_BLOCKED','verb',
  'seket','sa2et','we2e3','ta7','nzal','ska3',
  'A/B/A/B/B/B','سقط / وقع',
  '2=ق in sa2et and we2e3; seket most natural Lebanese')
w('حفروا / حفرت','they dug / was dug','ROADS','ROAD_BLOCKED','verb',
  '7afrou','3am yi7fru','7afaret','7afaro','shi 7afar','3am ti7fur',
  'A/A/A/A/B/B','حفروا',
  '7=ح required throughout; 3=ع in 3am')
w('انحرفت','swerved / veered','ROADS','POTHOLE','verb',
  'n7arafet','tin7arif','3am tin7arif','n7araf','in7araf','in7arafet',
  'A/A/A/A/C/C','انحرفت',
  'CRITICAL: 7=ح always — NEVER tinhirif/inhirif (omits ح); 3=ع in 3am')
w('تكسرت','broke apart (surface)','ROADS','ROAD_CRACK','verb',
  'nkasaret','tkassr','ttsarrat','nkasar','tkassaret','',
  'A/A/B/B/C','تكسرت',
  'nkasaret most natural for road surface breaking apart')

# ══════════════════════════════════════════════════════════════
# ROADS — ADJECTIVES
# ══════════════════════════════════════════════════════════════
w('مسدود / مقطوع','blocked / closed','ROADS','ROAD_BLOCKED','adjective',
  'masduud','ma2tou3','msakkar','maftoum','msadd','m2affel',
  'A/A/B/B/C/C','مسدود / مقطوع',
  '2=ق in ma2tou3 and m2affel; msakkar = locked; maftoum widely used')
w('متشقق','cracked (surface)','ROADS','ROAD_CRACK','adjective',
  'metshe22a2','mtsha22a2','mesho22','tshe22','nkassar','m2asha3',
  'A/B/C/C/B/C','متشقق',
  '2=ق throughout; metshe22a2 most natural')
w('مهالك / خرب','ruined / destroyed','ROADS','ROAD_DAMAGE','adjective',
  'ma7loul','ma7loule','5arban','5arbe','kharban','me7loul',
  'A/A/A/A/B/C','مهالك / خرب',
  '5=خ in 5arban; ma7loul most Lebanese for completely ruined; 7=ح')
w('ناقص / مفقود','missing / absent','ROADS','MISSING_MANHOLE','adjective',
  'mafqoud','na2es','ghayyeb','ma fi','ghayyab','mish mawjoud',
  'A/A/B/A/B/A','مفقود / ناقص',
  '2=ق in na2es; mafqoud most natural; ghayyeb = absent (informal)')
w('زلق / منزلق','slippery','ROADS','ROAD_DAMAGE','adjective',
  'zale2','zale2a','zaliq','mzale2','5atir zale2','',
  'A/A/B/B/A','زلق',
  '2=ق in zale2/zaliq; dangerous condition especially when wet')
w('مرتفع / منتفخ','raised / bulging (road surface)','ROADS','ROAD_DAMAGE','adjective',
  'mnantekh','nante5','mntfe5','nfokha','7ader myen7am','',
  'A/B/B/C/C','منتفخ / مرتفع',
  '5=خ in nante5; 7=ح in 7ader; bulging asphalt common complaint')
w('ضيق','narrow','ROADS','ALL','adjective',
  'daye2','daye2a','day2','diy2','mish wase3','',
  'A/A/B/B/A','ضيق',
  '2=ق in daye2/day2; daye2 most natural Lebanese')

# ══════════════════════════════════════════════════════════════
# WATER — NOUNS (expanded)
# ══════════════════════════════════════════════════════════════
w('مياه / ماء','water','WATER','ALL','noun_infra',
  'may','mai','ma2','maye','l may','may ta3na',
  'A/B/C/B/A/A','مياه / ماء',
  'may universal; may ta3na = our water; ma2 MSA; maye variant; 2=ق')
w('أنبوب','pipe','WATER','PIPE_LEAK','noun_infra',
  'anboub','inboub','anboob','inboob','anabib','l anboub',
  'A/B/B/C/B/A','أنبوب / أنابيب',
  'anboub most standard; anabib = pipes plural')
w('مضخة','pump (water/sewage)','WATER','ALL','noun_infra',
  'madde','pompe','pompit','maddit l may','moteur','motor',
  'A/A/B/A/B/B','مضخة',
  'madde most Lebanese (مضخة); pompe French loanword very common; moteur/motor also used for pump')
w('محبس / صمام','valve / shutoff','WATER','ALL','noun_infra',
  '7abbes','7abbese','samamm','valve','robinet','l 7abbes',
  'A/A/B/A/B/A','محبس / صمام',
  '7=ح in 7abbes; robinet French loanword; valve English loanword')
w('صنبور / حنفية','tap / faucet','WATER','ALL','noun_infra',
  '7anafiye','7anfiye','sanabir','sanboura','7anfiyit','sanboure',
  'A/A/B/B/C/B','حنفية / صنبور',
  '7=ح in 7anafiye; sanabir = plural; sanboure Bekaa variant')
w('خزان مياه','water tank / reservoir','WATER','WATER_CUT','noun_infra',
  'khazzen','5azzen','khazzan','5azzan','l khazzen','5azzenet l may',
  'A/B/A/B/A/A','خزان مياه',
  '5=خ preferred in seeds; khazzen also very common form')
w('صهريج / تانكر','water tanker truck','WATER','WATER_CUT','noun_infra',
  'tanker','tankar','sa7riij','sa7rij','l tanker','tanker may',
  'A/A/A/A/A/A','صهريج',
  'tanker English loanword dominant; sa7riij more formal Arabic term')
w('تسرب','leak (noun)','WATER','PIPE_LEAK','noun_infra',
  'tasarroub','tsarroub','sarroub','masroubet','tasarroub l may','tba3',
  'A/B/C/B/A/B','تسرب',
  'tasarroub most natural; tba3 = seeping (verb used as noun)')
w('كسر أنبوب','pipe burst','WATER','PIPE_LEAK','noun_infra',
  'anboub nkassar','kasret anboub','infijar anboub','anboub mfajar','anboub fatah','',
  'A/A/B/B/B','كسر أنبوب / انفجار أنبوب',
  'anboub nkassar most natural description; infijar = explosion/burst')
w('وصلة أنابيب','pipe joint / connector','WATER','PIPE_LEAK','noun_infra',
  'wasle','wasleh','waslet anabib','raccord','raccord l anboub','jonction',
  'A/A/A/B/B/C','وصلة أنابيب',
  'wasle most natural; raccord French loanword common in plumbing')
w('شبكة مياه','water grid / network','WATER','ALL','noun_infra',
  'shabket l may','l shabke','shabket l miyah','l shabke l asasiye','shabkit may','',
  'A/A/C/B/A','شبكة مياه',
  'shabke = network; no Arabizi markers needed in shabke')
w('عداد مياه','water meter','WATER','ALL','noun_infra',
  '3adad may','l 3adad','3adad l may','compteur may','3adad BMLWE','',
  'A/A/A/B/A','عداد مياه',
  '3=ع required; compteur French loanword; 3adad most common')
w('جدول المياه','water rationing schedule','WATER','WATER_CUT','noun_infra',
  'jadwal l may','maw3id l may','sa3et l may','yom l may','jadwal l BMLWE','',
  'A/A/A/A/A','جدول المياه',
  'UNIQUE LEBANESE: water supply rationed by hours/days per neighborhood; sa3et = hours; yom = day')
w('مياه مالحة','salty water','WATER','DIRTY_WATER','noun_infra',
  'may mal7a','may bi tal3at mil7','may m-mal7a','may ta3ma mish mne7','','',
  'A/B/B/B','مياه مالحة',
  '7=ح in mal7a; mal7 = salt; may m-mal7a = salty water (contracted)')
w('مياه بنية / صدئة','brown / rusty water','WATER','DIRTY_WATER','noun_infra',
  'may sawda','may bniyi','may fi 7atta','may msaddiyi','may bi lawn','may wane l lawn',
  'A/A/B/B/A/A','مياه بنية / صدئة',
  '7=ح in 7atta; bniyi = brown; msaddiyi = rusty (from iron pipes)')
w('مياه بيضاء / حليبية','milky / white water','WATER','DIRTY_WATER','noun_infra',
  'may bayde','may milkiyye','may fi mazij hawa','may 3ayniyi','may 3atma','',
  'A/B/B/B/C','مياه بيضاء',
  '3=ع in 3ayniyi; may bayde = white water; hawa = air (dissolved air causes white water)')
w('رغوة في الماء','foam in water','WATER','DIRTY_WATER','noun_infra',
  'raghwe bi l may','rghwe','may fi rghwe','zbad bi l may','may rghwiye','',
  'A/B/A/B/B','رغوة في المياه',
  'raghwe = foam; zbad = foam/suds; may rghwiye = foamy water')
w('رائحة كلور','chlorine smell in water','WATER','DIRTY_WATER','noun_infra',
  'ri7et klor','ri7et clore','ri7et l may bi klor','may bi ri7et madde','may tnin l ri7a','',
  'A/A/A/B/B','رائحة كلور',
  '7=ح in ri7et; klor = chlorine; complaint about excess chlorination')
w('طعم غريب','strange taste (water)','WATER','DIRTY_WATER','noun_infra',
  'ta3met gharibe','ta3m mish mni7','ta3m may 5arbe','ta3m may wse5','','',
  'A/A/A/A','طعم غريب',
  '3=ع in ta3met; 5=خ in 5arbe; mish NOT mesh')
w('ضغط المياه','water pressure','WATER','LOW_PRESSURE','noun_infra',
  'daght l may','daght l maya','l daght','daght khafif','daght na2es','daght sefir',
  'A/B/A/A/A/B','ضغط المياه',
  '2=ق in na2es; daght = pressure; sefir = zero (South Lebanon variant)')
w('مياه ساخنة','hot water','WATER','ALL','noun_infra',
  'may su5ne','may s5ene','may 7amine','may sa5ne','l may s5ene','',
  'A/A/B/B/A','مياه ساخنة',
  '5=خ in su5ne; 7=ح in 7amine; su5ne most natural Beiruti')
w('سخان مياه','water heater','WATER','ALL','noun_infra',
  'sa55an','sa5an','l sa55an','sa55an l may','chauffe-eau','sa55eneh',
  'A/A/A/A/B/C','سخان',
  '5=خ in sa55an; chauffe-eau French term also very common in Lebanon')
w('مجرى / قناة','water channel / canal','WATER','ALL','noun_infra',
  'majra','l majra','2ana','2anat may','2anat sarf','kanal',
  'A/A/B/B/B/B','مجرى / قناة',
  '2=ق in 2ana; majra most common; kanal French loanword (canal)')
w('بيارة / حفرة صرف','septic pit / cesspool','WATER','SEWAGE_OVERFLOW','noun_infra',
  'biyara','l biyara','7ofret sarf','fosse','fosse sceptique','7afret sarif',
  'A/A/A/B/B/B','بيارة / حفرة صرف',
  '7=ح in 7ofret; fosse/fosse sceptique French terms common in rural Lebanon')
w('مياه صرف صحي','sewage water','WATER','SEWAGE_OVERFLOW','noun_infra',
  'may sarif','may l mrajir','may l majari','may l sarif l sa77i','may 5anze','',
  'A/A/A/A/B','مياه صرف صحي',
  '7=ح in sa77i; 5=خ in 5anze; may sarif most compressed natural form')
w('تلوث مصدر مياه','water source contamination','WATER','DIRTY_WATER','noun_infra',
  'may mla2wate men l asas','tlayyout masdar l may','may masdar 5arban','','','',
  'A/B/C','تلوث مصدر المياه',
  '5=خ in 5arban; tlayyout = contamination; most critical water issue')
w('انقطاع المياه','water cutoff (state)','WATER','WATER_CUT','noun_infra',
  '2ata2 l may','2at3 may','inkata3 l may','ma fi may','may ma rja3et','may 2at3a',
  'A/A/A/A/A/A','انقطاع المياه',
  '2=ق in 2ata2 and 2at3; may 2at3a = water is cut (adj+noun)')
w('صرف صحي','sewage / sanitation','WATER','SEWAGE_OVERFLOW','noun_infra',
  'sarif sa77i','sarf sa77i','sarif s7i','l sarif','sarf s7i','l mrajir',
  'A/A/B/B/C/B','صرف صحي',
  'sa77i double-7 correct for صحي; s7i compressed variant')
w('رائحة صرف','sewage smell','WATER','SEWAGE_OVERFLOW','noun_infra',
  'ri7et sarif','ri7a sarif','ri7et l sarif','ri7et mrajir','ri7a sarif sa77i','ri7a l majari',
  'A/B/A/C/B/C','رائحة صرف',
  '7=ح in ri7et; ri7et sarif most natural')
w('بالوعة','drain (general)','WATER','SEWAGE_OVERFLOW','noun_infra',
  'balioa','balou3a','baliwa','balouwa','balou3','bl3a',
  'A/B/B/C/B/C','بالوعة',
  'balioa most common Beiruti; bl3a ultra-contracted; 3=ع in balou3a')
w('مرسوب / متسرب','overflowing/seeping (sewage)','WATER','SEWAGE_OVERFLOW','adjective',
  '3am yetfa2ar','3am yetfayan','3am yifur','tfa2ar','msarrib','yfur',
  'A/A/B/B/B/C','يتفجر / يتسرب',
  '2=ق in yetfa2ar; 3=ع in 3am; yetfa2ar = bursting out')

# ══════════════════════════════════════════════════════════════
# WATER — VERBS
# ══════════════════════════════════════════════════════════════
w('انقطع (مياه/كهرباء)','cut off — water or power','WATER','WATER_CUT','verb',
  '2ata3et','inkata3et','2it3et','nkata3et','2at3a','2ataet',
  'A/B/B/B/A/C','انقطع',
  '2=ق most used; 2ata3et single most common Lebanese form for water/power cut')
w('رجعت (مياه/كهرباء)','came back — water or power','WATER','WATER_CUT','verb',
  'rja3et','rja3','raja3et','rja3at','3adet','rja3et l 7amdillah',
  'A/A/B/B/C/A','رجعت',
  '3=ع in 3adet and l 3amdillah; rja3et most common Lebanese')
w('يتسرب','leaking (ongoing)','WATER','PIPE_LEAK','verb',
  '3am yesarrab','3am yitsarrab','3am yitba3','3am yitfa2ar','3am ynazzel','sarrab',
  'A/A/B/B/B/B','يتسرب',
  '2=ق in yitfa2ar; 3=ع in 3am; yitba3 = seeping; yitfa2ar = gushing')
w('يضخ','pumps water','WATER','ALL','verb',
  'yda55','3am yda55','shegghalo l madde','da55o l may','3am yishghel l madde','',
  'A/A/A/A/A','يضخ',
  '5=خ in da55; 3=ع in 3am; yda55 most natural for pumping')
w('يقطع المياه','cuts off water','WATER','WATER_CUT','verb',
  'yi2ta3 l may','yi2te3','yi2ta3on','yi2ta3 3an l 7ayye','','',
  'A/A/B/A','يقطع المياه',
  '2=ق in yi2ta3; 3=ع in 3an; 7=ح in 7ayye')
w('يلوث','contaminates','WATER','DIRTY_WATER','verb',
  'ylayyit','ylayyot','3am ylayyit','layyat','3am ylayyotu','',
  'A/A/A/B/A','يلوث',
  '3=ع in 3am; ylayyit most natural Lebanese')
w('يفور / يطغى','overflows / gushes','WATER','SEWAGE_OVERFLOW','verb',
  '3am yifur','3am yetfa2ar','3am yetfayan','3am yefid','far','tafan',
  'A/A/A/B/B/B','يفور / يطغى',
  '2=ق in yetfa2ar; 3=ع in 3am; yifur most natural for gushing; tafan = overflowed')
w('ينكسر / ينفجر','breaks / bursts (pipe)','WATER','PIPE_LEAK','verb',
  'nkassar','nfajar','fa2a3','ta2a3','fat7','inkasar',
  'A/B/B/B/B/C','ينكسر / ينفجر',
  '2=ق in fa2a3/ta2a3; nkassar most natural; nfajar = burst')

# ══════════════════════════════════════════════════════════════
# ELECTRICITY — NOUNS (expanded)
# ══════════════════════════════════════════════════════════════
w('كهرباء','electricity','ELECTRICITY','ALL','noun_infra',
  'kahraba','kahrabe','kehraba','kahraba2','khrba','l kahraba',
  'A/A/B/C/C/A','كهرباء',
  'kahraba most common; kahrabe spoken feminine; khrba ultra-contracted; 2=ء glottal')
w('سلك / حبل كهربائي','electrical wire / cable','ELECTRICITY','EXPOSED_WIRE','noun_infra',
  'silk kahraba','7abal kahraba','silk','7abal','selk','7bal',
  'A/A/A/A/B/B','سلك / حبل كهربائي',
  '7=ح in 7abal; silk = wire/thread; 7abal = cable/rope; both very common')
w('محول','transformer','ELECTRICITY','TRANSFORMER_FAULT','noun_infra',
  'muhawwel','m7awwel','mohawwel','mu7awwel','l muhawwel','sandou2 kahraba',
  'A/A/B/B/A/B','محول',
  '7=ح in m7awwel/mu7awwel; sandou2 = box (the transformer box)')
w('مولد كهربائي','electrical generator','ELECTRICITY','ALL','noun_infra',
  'moualid','moulid','walid','l moualid','generator','generateur',
  'A/B/B/A/B/B','مولد كهربائي',
  'moualid most common Lebanese; generator English; générateur French')
w('عمود كهرباء','electricity pole','ELECTRICITY','EXPOSED_WIRE','noun_infra',
  '3amoud kahraba','3amoud','poteau','3amoud l kahraba','3amood kahraba','l 3amoud',
  'A/A/B/A/B/A','عمود كهرباء',
  '3=ع required; poteau French loanword very common')
w('فيوز / قاطع','fuse / circuit breaker','ELECTRICITY','POWER_OUTAGE','noun_infra',
  'fiyo','fyou','fuse','2ate3','disjoncteur','l 2ate3',
  'A/A/A/B/B/A','فيوز / قاطع',
  'fiyo most Lebanese; fuse English; disjoncteur French; 2=ق in 2ate3')
w('لمبة / مصباح','light bulb / lamp','ELECTRICITY','STREET_LIGHT','noun_infra',
  'lampe','l lampe','lampit','masba7','ampoule','masabi7',
  'A/A/B/A/B/B','لمبة / مصباح',
  'lampe French loanword dominant; masba7 more MSA (7=ح); ampoule French also used')
w('بريز / وصلة كهرباء','power socket / outlet','ELECTRICITY','ALL','noun_infra',
  'briz','brees','prise','briz kahraba','prize','l briz',
  'A/B/A/A/B/A','بريز / مقبس',
  'briz French loanword (prise) dominant in Lebanese')
w('جدول الكهرباء','electricity rationing schedule','ELECTRICITY','POWER_OUTAGE','noun_infra',
  'jadwal l kahraba','jadwal l EDL','jadwal l 2ata3','maw3id l kahraba','sa3et l kahraba','sa3et l dawle',
  'A/A/A/B/B/A','جدول الكهرباء',
  'UNIQUE LEBANESE: electricity rationed by zone and hours; sa3et l dawle = state electricity hours')
w('أمبير موالد','generator ampere tier','ELECTRICITY','ALL','noun_infra',
  'amper moualid','amper l walid','amper ta3na','l amper','amper ktir','amper 2alil',
  'A/A/A/B/A/A','أمبير المولد',
  'UNIQUE LEBANESE: subscriptions to private generators are sold in ampere units')
w('ساعات الكهرباء','electricity hours','ELECTRICITY','POWER_OUTAGE','noun_infra',
  'sa3et l kahraba','sa3et l EDL','kam sa3a 3andkon','sa3et l dawle','sa3et l moualid','ka2adet l kahraba',
  'A/A/A/A/A/B','ساعات الكهرباء',
  '3=ع in 3andkon; kam sa3a = how many hours — the classic Lebanese complaint question')
w('انقطاع كهرباء','power outage','ELECTRICITY','POWER_OUTAGE','noun_infra',
  '2ata2 kahraba','2at3 kahraba','kahraba 2ata3et','kahraba 2at3a','3atme','inkata3et',
  'A/A/A/A/A/B','انقطاع كهرباء',
  '2=ق throughout; 3atme = darkness (also means power cut); 3=ع')
w('عتمة / ظلام','darkness / blackout','ELECTRICITY','POWER_OUTAGE','noun_infra',
  '3atme','3etme','dalma','zalma','3atma','3etmet tari2',
  'A/B/B/B/C/B','عتمة',
  '3=ع in 3atme; dalma South Lebanon; zalma Bekaa/South; 3atmet tari2 = dark road')
w('تذبذب كهربائي','voltage fluctuation','ELECTRICITY','VOLTAGE_FLUCTUATION','noun_infra',
  'tazabzob','l tazabzob','tazabzob kahraba','tzabzob','fi tazabzob','',
  'A/A/A/B/A','تذبذب',
  'no Arabizi markers in this root; tazabzob is very recognizable')
w('فولت','volt','ELECTRICITY','VOLTAGE_FLUCTUATION','noun_infra',
  'volt','l volt','volt na2es','volt zayed','volt wafe2','tazabzob l volt',
  'A/A/A/B/B/A','فولت',
  '2=ق in na2es; na2es = insufficient; zayed = excess; wafe2 = correct (220V)')
w('أمبير','ampere','ELECTRICITY','VOLTAGE_FLUCTUATION','noun_infra',
  'amper','ampere','l amper','amper na2es','amper zayed','amper wafe2',
  'A/A/A/A/B/B','أمبير',
  '2=ق in na2es; amper most Lebanese spelling')
w('شرارة','spark / sparks','ELECTRICITY','EXPOSED_WIRE','noun_infra',
  'sharara','shrarit','shararaat','fi sharara','shararet kahraba','brq kahraba',
  'A/B/B/A/A/C','شرارة / شرر',
  'sharara = one spark; shrarit = sparks; brq = lightning (used for sparks in very casual Arabizi)')
w('احتراق / حرق','burning / combustion','ELECTRICITY','TRANSFORMER_FAULT','noun_infra',
  'i7tira2','7ar2','7ar2 kahraba','7ar2 silk','7ar2 muhawwel','ri7et 7ar2',
  'A/A/A/A/A/A','احتراق',
  '7=ح required throughout; i7tira2 most formal')
w('طنين / صرير','humming / buzzing noise','ELECTRICITY','TRANSFORMER_FAULT','noun_infra',
  'tanin','tanin kahraba','sreer','sawt 3ajib','sawt wazwaze','',
  'A/A/B/B/B','طنين / صرير',
  '3=ع in 3ajib; tanin = humming; sreer = buzzing/crackle from transformer')
w('توصيلات عشوائية','illegal / random connections','ELECTRICITY','ALL','noun_infra',
  'tawsilat 3ashwe2iye','tawsilat 3eshwaiye','silk 7aram','silk meshbouk','tawsilat mish 2anoune','',
  'A/A/A/B/B','توصيلات عشوائية',
  '3=ع in 3ashwe2iye; 2=ق in 2anoune; 7=ح in 7aram; common issue in informal settlements')
w('إنارة عامة','street lighting','ELECTRICITY','STREET_LIGHT','noun_infra',
  'nour share3','nour l share3','nour 3aam','isharet nour','l eclairage','nour l 7ayye',
  'A/A/B/B/C/A','إنارة عامة',
  '3=ع in 3aam; 7=ح in 7ayye; eclairage French loanword')
w('صدمة كهربائية','electric shock','ELECTRICITY','EXPOSED_WIRE','noun_infra',
  'sadmet kahraba','sa32 kahraba','sa32','insadamet bi l kahraba','','',
  'A/A/A/B','صدمة كهربائية',
  'sa32 = electrocution; sadmet kahraba most formal description')
w('حريق كهربائي','electrical fire','ELECTRICITY','ALL','noun_infra',
  '7ariki kahraba','7ar2 silk','7ariki men l kahraba','7ar2 kahrabe','7areki men silk','',
  'A/A/A/A/A','حريق كهربائي',
  '7=ح throughout; 7ariki kahraba most natural')
w('اتصال أرضي / قصر كهربائي','short circuit / ground fault','ELECTRICITY','ALL','noun_infra',
  '2asr kahrabe','2asr','court-circuit','courant terre','silk m2assar','silk bi l ard',
  'A/A/B/B/B/A','قصر كهربائي',
  '2=ق in 2asr; court-circuit French loanword used by technicians')
w('عداد كهرباء','electricity meter','ELECTRICITY','ALL','noun_infra',
  '3adad kahraba','l 3adad','compteur kahraba','3adad l EDL','3adad l dawle','3adad l moualid',
  'A/A/B/A/B/A','عداد كهرباء',
  '3=ع required; compteur French loanword')
w('تلف أجهزة','appliance damage from voltage','ELECTRICITY','VOLTAGE_FLUCTUATION','noun_infra',
  'i7tira2 ajhize','7ar2 til l ajhize','ajhize ni7ra2et','i7tira2 frigider','i7tira2 TV','',
  'A/A/A/B/B','تلف الأجهزة',
  '7=ح throughout; very common complaint when voltage spikes; frigider/TV loanwords')

# ══════════════════════════════════════════════════════════════
# ELECTRICITY — VERBS
# ══════════════════════════════════════════════════════════════
w('انقطع (كهرباء)','cut off — electricity','ELECTRICITY','POWER_OUTAGE','verb',
  'kahraba 2ata3et','2ata3et','inkata3et','kahraba 2at3a','3atme siyet','nkata3et',
  'A/A/B/A/A/B','انقطع',
  '2=ق in 2ata3et; 3=ع in 3atme; 2ata3et most common Lebanese')
w('رجعت (كهرباء)','came back — electricity','ELECTRICITY','POWER_OUTAGE','verb',
  'kahraba rja3et','rja3et','rja3 l kahraba','3ado l kahraba','l kahraba 2enit','',
  'A/A/A/B/C','رجعت',
  '3=ع in 3ado; rja3et most natural form')
w('يتذبذب','fluctuates (voltage)','ELECTRICITY','VOLTAGE_FLUCTUATION','verb',
  '3am titba3 w troo7','3am tji w troo7','3am yitzabzab','fi tazabzob','kahraba msh stable','',
  'A/A/B/A/A','يتذبذب',
  '3=ع in 3am; tji w troo7 = comes and goes; msh stable English loanword use authentic')
w('انفجر المحول','transformer exploded','ELECTRICITY','TRANSFORMER_FAULT','verb',
  'muhawwel nfajar','nfajar l muhawwel','muhawwel 3am yithal','muhawwel ni7ra2','','',
  'A/A/A/A','انفجر المحول',
  '7=ح in yithal; nfajar most natural for explosion')
w('نزل / سقط (سلك)','fell — wire dropped to ground','ELECTRICITY','EXPOSED_WIRE','verb',
  'nzal 3al ard','2eta3 w nzal','ta7 3al ard','nkazal','seket 3al ard','nzal l silk',
  'A/A/B/B/A/A','نزل / سقط',
  '3=ع in 3al; 2=ء in 2eta3; nzal most natural')

# ══════════════════════════════════════════════════════════════
# WASTE — NOUNS (expanded)
# ══════════════════════════════════════════════════════════════
w('زبالة','garbage / rubbish','WASTE','ALL','noun_infra',
  'zbele','zbale','nfayat','nfaye','zbeleh','zbali',
  'A/B/A/B/C/C','زبالة / نفايات',
  'zbele most Beiruti; zbali Bekaa variant; nfayat formal/MSA; zbale North Lebanon')
w('حاوية / قلبة','waste bin / skip container','WASTE','ALL','noun_infra',
  '7awiye','2lebe','sandou2 zbele','7awiyit zbele','l 7awiye','7awiyat',
  'A/A/B/A/A/B','حاوية / قُلَّبة',
  '7=ح in 7awiye; 2=ق in 2lebe; 7awiyat = plural; sandou2 = box')
w('كومة نفايات','garbage pile','WASTE','ILLEGAL_DUMP','noun_infra',
  'kuumet zbele','kuumet nfayat','rkme zbele','rakme zbele','talle zbele','masabb zbele',
  'A/A/B/B/C/B','كومة نفايات',
  'kuumet zbele most natural; masabb = dump site; talle = mound')
w('مكب نفايات','dump site','WASTE','ILLEGAL_DUMP','noun_infra',
  'masabb','mkabb','masab nfayat','masabb zbele','décharge','',
  'A/B/A/A/B','مكب نفايات',
  'masabb most Lebanese; décharge French loanword also used')
w('إنكاش / حطام بناء','construction debris / rubble','WASTE','ILLEGAL_DUMP','noun_infra',
  'nkesh','inkesh','inkash','nkesh bine','2anqad','5arabe',
  'A/A/B/A/C/B','إنكاش / حطام',
  '5=خ in 5arabe (ruins); 2=ق in 2anqad; nkesh most Lebanese for construction debris')
w('ردم / تراب','fill material / dumped soil','WASTE','ILLEGAL_DUMP','noun_infra',
  'radm','l radm','radm w nkesh','trab','trab w nkesh','ard marmiye',
  'A/A/A/A/A/B','ردم / تراب',
  'radm = fill material; trab = soil/dust; ard marmiye = dumped earth')
w('أثاث قديم','old furniture (dumped)','WASTE','ILLEGAL_DUMP','noun_infra',
  'asas 2adim','asas marmiye','asas msoubet','furniture marmiye','asas','l asas',
  'A/A/A/B/B/A','أثاث قديم',
  '2=ق in 2adim; asas most Lebanese for household furniture; marmiye = thrown away')
w('إطارات سيارات','dumped car tires','WASTE','ILLEGAL_DUMP','noun_infra',
  'dwalib marmiye','dalab zbele','tires marmiye','dwalib 2adme','', '',
  'A/A/B/A','إطارات سيارات',
  '2=ق in 2adme; dwalib most Lebanese for tires; tires English loanword also used')
w('بلاستيك','plastic waste','WASTE','ALL','noun_infra',
  'blastik','l blastik','plastique','blestik','akyas blastik','plastik',
  'A/A/A/B/A/B','بلاستيك',
  'blastik most Lebanese; plastique French variant; akyas = bags')
w('زجاج مكسور','broken glass','WASTE','ALL','noun_infra',
  'zje2 maksour','zje2 mkasar','zje2 marmiye','zje2','kaasat mekshoure','',
  'A/A/A/B/B','زجاج مكسور',
  '2=ق in zje2 (Lebanese pronunciation of زجاج); kaasat = glasses/vessels')
w('نفايات طبية','medical waste','WASTE','ILLEGAL_DUMP','noun_infra',
  'nfayat tibbiye','zbele mustashfa','nfayat 5atere','zbele 7asharat tibbiye','zbele tibbi','',
  'A/B/A/C/A','نفايات طبية',
  '5=خ in 5atere; mustashfa = hospital; tibbiye/tibbi = medical')
w('نفايات صناعية','industrial waste','WASTE','ILLEGAL_DUMP','noun_infra',
  'nfayat sina3iye','zbele masna3','mawad kimyaiye','mawad sam','nfayat masna3','',
  'A/A/B/A/A','نفايات صناعية',
  '3=ع in sina3iye; sam = toxic/poisonous')
w('مواد كيميائية','chemical materials / hazmat','WASTE','ILLEGAL_DUMP','noun_infra',
  'mawad kimyaiye','kimyawi','mawad 5atere','kimyawi mshkob','mawad seliyi','',
  'A/A/A/B/B','مواد كيميائية',
  '5=خ in 5atere; mshkob = spilled; seliyi = liquid (chemicals)')
w('رائحة تعفن','smell of decomposition','WASTE','OVERFLOWING_BIN','noun_infra',
  'ri7et ta3affun','ri7et fasad','ri7et fased','ri7a bayse','ri7a zbaleh','ri7a keri7a',
  'A/A/A/A/B/B','رائحة تعفن',
  '7=ح in ri7et; 3=ع in ta3affun; fased = rotten; bayse = spoiled; keri7a MSA-influenced')
w('حرق نفايات','burning waste','WASTE','BURNING_WASTE','noun_infra',
  '7ar2 zbele','7ar2 nfayat','3am yi7arkou zbele','7ariki zbele','ri7et 7ar2 zbele','',
  'A/A/A/A/A','حرق نفايات',
  '7=ح required throughout; 7ar2 most natural noun form')
w('دخان من حرق','smoke from burning waste','WASTE','BURNING_WASTE','noun_infra',
  'dukhan','dukhin','dukhaan','ri7et 7ar2','dukhan zbele','dkhaan zbele',
  'A/B/A/A/A/B','دخان',
  '7=ح in ri7et; dukhan most common; dukhaan/dkhaan emphasis forms')
w('حشرات وقوارض','insects and rodents (from waste)','WASTE','OVERFLOWING_BIN','noun_infra',
  '7asharat','far','7asharat w far','2lab 7aliyye','7ashr w 7ashr','far w 7asharat',
  'A/A/A/B/B/A','حشرات وقوارض',
  '7=ح in 7asharat; 2=ق in 2lab = dogs; far = rat (singular common)')
w('أكياس ممزقة','torn garbage bags','WASTE','GARBAGE_NOT_COLLECTED','noun_infra',
  'akyas mfatta7a','akyas mmazza2a','kis zbele ftah','akyas kasser','akyas nkasaret','',
  'A/A/A/B/B','أكياس ممزقة',
  'mfatta7a = opened/torn; mmazza2a = ripped; 7=ح in mfatta7a')
w('رائحة حارقة','burning smell (waste fire)','WASTE','BURNING_WASTE','noun_infra',
  'ri7et 7ar2','ri7a 7arke','ri7et 7ariki','ri7et dukhan','ri7a nnar','',
  'A/A/A/A/A','رائحة حارقة',
  '7=ح throughout; 7arke = burning; all natural forms')

# ══════════════════════════════════════════════════════════════
# FLOODING — NOUNS (expanded)
# ══════════════════════════════════════════════════════════════
w('سيل / فيضان','flash flood / flood','FLOODING','FLASH_FLOOD','noun_infra',
  'seyle','seyl','fayadan','sayleh','seyle kbire','seil',
  'A/B/C/C/A/C','سيل / فيضان',
  'seyle most Lebanese for flash flood; fayadan formal; seyle kbire = big flash flood')
w('مياه طينية','muddy water','FLOODING','FLASH_FLOOD','noun_infra',
  'may wse5a','may 3akere','may bi tine','may 7amra','may 3tiyke','may m5alata bi tine',
  'A/A/A/B/B/B','مياه طينية',
  '5=خ in m5alata; 3=ع in 3akere (turbid); 7=ح in 7amra (reddish clay water); wse5a = dirty')
w('مطر غزير','heavy rain','FLOODING','FLASH_FLOOD','noun_infra',
  'mtar gzir','mtar ktir','mtar 3asife','matar 7amid','mtar 7amel','mtar wajib',
  'A/A/A/B/B/A','مطر غزير',
  '7=ح in 7amid (heavy rain); 3=ع in 3asife; gzir = copious/heavy; wajib = heavy')
w('بالوعة مسدودة','blocked drain','FLOODING','BLOCKED_DRAIN','noun_infra',
  'balioa masduude','balioa msakkarit','balioa ma 3am tishrab','balioa mashloume','balioa mtenniyye','',
  'A/A/A/A/B','بالوعة مسدودة',
  '3=ع in 3am; balioa masduude most natural; tishrab = absorbing water (Lebanese metaphor)')
w('مياه راكدة / واقفة','standing water / puddle','FLOODING','STANDING_WATER','noun_infra',
  'may wa2fe','may rake2a','may mish raye7a','birke may','may 3am twa22ef','may nssebe',
  'A/B/A/A/B/B','مياه راكدة',
  '2=ق in wa2fe and wa22ef; mish NOT mesh; rake2a = stagnant (formal)')
w('قبو / تحت الأرض','basement / underground','FLOODING','BASEMENT_FLOODED','noun_infra',
  '2abi','abi','l 2abi','l 2abi ta7t','2abi l bnayi','ta7t l bnayi',
  'A/B/A/A/B/A','قبو',
  '2=ق; NOTE: 2abu = father of — different word entirely; only 2abi/abi for basement')
w('شخص محاصر','trapped person','FLOODING','FLASH_FLOOD','noun_person',
  '7ada ma7sour','7ada 3alqan','7ada msh 2adir yi5roj','7ada ma2sour','7ada bel seyle','',
  'A/A/A/A/A','شخص محاصر',
  '7=ح in 7ada; 2=ق in 2adir and ma2sour; 5=خ in yi5roj; extremely urgent')
w('سيارة غارقة','submerged / flooded car','FLOODING','FLASH_FLOOD','noun_infra',
  'sayyara ghare2a','sayyara fi l may','sayyara gharet','sayyara tayyit','sayyara ma2le may','',
  'A/A/A/A/A','سيارة غارقة',
  '2=ق in ghare2a/tayyit; gharet = was flooded; ma2le may = filled with water')
w('إخلاء طارئ','emergency evacuation','FLOODING','FLASH_FLOOD','noun_infra',
  'ikhla2','i5la2','ikhla2 3aajel','3am yi5lou l nass','l nass 3am t7arrab','',
  'A/B/A/A/A','إخلاء',
  '2=ء in ikhla2/i5la2; 5=خ in i5la2; 3=ع in 3am; 7=ح in t7arrab')
w('مياه جوفية','groundwater','FLOODING','ALL','noun_infra',
  'may jawfiye','may men ta7t l ard','may taht l ard','may 2asasiye','may men ta7t','',
  'A/A/A/C/A','مياه جوفية',
  '7=ح in ta7t; may men ta7t l ard most natural explanation in Lebanese')
w('تسرب مياه في البناية','water seeping into building','FLOODING','HOUSE_FLOODED','noun_infra',
  'may 3am tetra2','reshoubet may','may 3am tiji men l 7etan','3am tetra2','may men l sa2f','',
  'A/B/A/A/A','تسرب مياه في البناية',
  '7=ح in 7etan; 3=ع in 3am; reshoubet = seepage; tetra2 = seeping through')
w('صرف مطر','storm drain / rainwater drainage','FLOODING','BLOCKED_DRAIN','noun_infra',
  'sarf matar','balioa l matar','sarf l amtar','msdou l matar','bortil','',
  'A/A/A/B/B','صرف مطر',
  'sarf matar most natural; bortil = large storm drain canal; msdou = blocked')
w('تدفق مياه','water flow / surge','FLOODING','FLASH_FLOOD','noun_infra',
  'tadfou2 may','tadfou2 l may','saret may','jarat may','may 3am tejri','',
  'A/A/A/A/A','تدفق مياه',
  '2=ق in tadfou2; 3=ع in 3am; saret = flowed; jarat = ran')

# ══════════════════════════════════════════════════════════════
# FLOODING — VERBS
# ══════════════════════════════════════════════════════════════
w('غرق / فاض','flooded / overflowed','FLOODING','ALL','verb',
  '3am yetfayan','gharet','tafan','3am yetfa2ar','2are2','ghara2',
  'A/A/A/A/B/C','غرق / فاض',
  '2=ق in 2are2 and ghara2; 3=ع in 3am; yetfayan most natural Lebanese')
w('انسد / امتلأ','blocked / filled up','FLOODING','BLOCKED_DRAIN','verb',
  'masduude','msadd','mli2et','mli2','mmtele','ta3abbat',
  'A/A/A/B/B/A','انسد / امتلأ',
  '2=ق in mli2et/mli2; ta3abbat = filled up (verb); mmtele = filled (adj)')
w('دخلت المياه','water entered','FLOODING','HOUSE_FLOODED','verb',
  'may dakhlet','dakhlet l may','may dakhalet 3al bayt','may dakhlet la jouwwa','may darrabet l bayt','da5let l may',
  'A/A/A/A/B/A','دخلت المياه',
  '3=ع in 3al; 5=خ in da5let; dakhlet most natural')
w('يتر / يتسرب (هيكل)','seeps through — building','FLOODING','HOUSE_FLOODED','verb',
  '3am yetra2','3am yitra2','3am ttetra2','bnayi 3am yetra2','men l sa2f 3am yetra2','',
  'A/B/A/A/A','يتر / يتسرب',
  '2=ء in yetra2; 3=ع in 3am; yetra2 specific Lebanese verb for water seeping through structures')

# ══════════════════════════════════════════════════════════════
# SAFETY — NOUNS (expanded)
# ══════════════════════════════════════════════════════════════
w('حريق','fire (incident)','SAFETY','FIRE','noun_infra',
  '7ariki','7areke','7ari2a','7ari2','nnar','fi nnar',
  'A/B/B/C/A/A','حريق',
  '7=ح required throughout; 7ariki most Lebanese colloquial')
w('انفجار','explosion','SAFETY','FIRE','noun_infra',
  'infijar','nfijar','nfejar','infijaar','nfijar kbir','2infijar',
  'A/B/C/C/A/C','انفجار',
  'infijar most natural; 2=ء in 2infijar formal')
w('غاز مسرَّب','leaked gas','SAFETY','GAS_LEAK','noun_infra',
  'ghaz 3am yetfassal','ri7et ghaz','ghaz mtsarrib','masroubet ghaz','ghaz mshkob','tasarroub ghaz',
  'A/A/B/B/B/A','غاز مسرَّب',
  '3=ع in 3am; ghaz 3am yetfassal most natural phrase')
w('هيكل / إطار هيكلي','structural frame / skeleton','SAFETY','STRUCTURAL_COLLAPSE','noun_infra',
  '7aykal','l 7aykal','haykel','7ikal','l 7aykal l asasi','2itar hayakli',
  'A/A/B/C/A/B','هيكل',
  'CRITICAL: 7aykal (7=ح) NOT hal which = هل interrogative; 7aykal = structural frame')
w('جدار / حيط','wall','SAFETY','STRUCTURAL_COLLAPSE','noun_infra',
  '7iit','7eet','7ita','jidar','hayit','7ayta',
  'A/A/B/B/C/C','جدار / حائط',
  '7=ح required; 7iit most Beiruti; jidar more MSA')
w('سقف','ceiling / roof','SAFETY','STRUCTURAL_COLLAPSE','noun_infra',
  'sa2f','sa2ef','sa2if','saqf','l sa2f','sa2f l bnayi',
  'A/B/C/C/A/A','سقف',
  '2=ق most common Lebanese; sa2f = ceiling; saqf MSA')
w('بناية / مبنى','building','SAFETY','STRUCTURAL_COLLAPSE','noun_infra',
  'bnayi','bnaye','bnayyeh','mabne','3amare','binyeh',
  'A/A/B/A/B/C','بناية / مبنى',
  'bnayi most Beiruti; mabne common; 3amare = apartment building (3=ع)')
w('أساسات','foundations','SAFETY','STRUCTURAL_COLLAPSE','noun_infra',
  '2asissat','l 2asissat','2asas l bnayi','fondations','2asasat l mabne','',
  'A/A/A/B/A','أساسات',
  '2=ء in 2asissat; fondations French loanword also used; cracked foundations = very urgent')
w('تشققات هيكلية','structural cracks','SAFETY','STRUCTURAL_COLLAPSE','noun_infra',
  'tashaddo2at bi l 7iit','tashaddo2at haykaliye','tashaddo2at bi l asas','tashaddo2at bi l sa2f','','',
  'A/B/A/A','تشققات هيكلية',
  '7=ح in 7iit; 2=ق throughout tashaddo2at')
w('سلاح / مسدس','weapon / gun','SAFETY','ARMED_INCIDENT','noun_infra',
  'sila7','musaddas','bundou2iye','pistol','sila7 nari','l sila7',
  'A/A/B/B/A/A','سلاح / مسدس',
  '7=ح in sila7; musaddas = pistol; bundou2iye = rifle')
w('طلق ناري','gunshot','SAFETY','ARMED_INCIDENT','noun_infra',
  'tal2a nariyi','tla2 nar','tar2a','tal2a','sme3na tla2','fi tla2',
  'A/A/A/B/A/A','طلق ناري',
  '2=ق in tal2a; 3=ع in sme3na (we heard); tla2 nar = shots fired')
w('إطلاق نار','shooting (ongoing)','SAFETY','ARMED_INCIDENT','noun_infra',
  'itla2 nar','tla2 nar','fi tla2 nar','3am yi2lo nar','ishkal masalla7','tla2 bi l 7ayye',
  'A/A/A/A/B/A','إطلاق نار',
  '2=ق in 2lo and itla2; 3=ع in 3am; 7=ح in 7ayye')
w('عراضة','celebratory shooting in air','SAFETY','ARMED_INCIDENT','noun_infra',
  '3arade','3rade','3aradet nar','tla2 bi l hawa','3arade bi l 7ayye','3aradet fara7',
  'A/A/A/B/A/B','عراضة',
  '3=ع required; UNIQUE LEBANESE/ARAB practice — celebratory shooting; dangerous; 7=ح in 7ayye')
w('شجار / إشكال','fight / brawl / incident','SAFETY','ARMED_INCIDENT','noun_infra',
  'ishkal','ishkale','shjar','sjaar','7arake','mas2ale amnieh',
  'A/A/B/B/B/B','شجار / إشكال',
  '7=ح in 7arake; ishkal most common Lebanese for street fight/incident')
w('سرقة','theft / robbery','SAFETY','SUSPICIOUS','noun_infra',
  'sar2a','sera2a','sar2it','fi sar2a','3am yisra2ou','7adet sar2a',
  'A/A/B/A/A/A','سرقة',
  '2=ق in sar2a; 3=ع in 3am; 7=ح in 7adet')
w('لص / حرامي','thief / burglar','SAFETY','SUSPICIOUS','noun_person',
  '7arami','ssare2','liss','lsous','7arame','sarrea2',
  'A/A/B/B/A/B','لص / حرامي',
  '7=ح in 7arami; 7arami most Lebanese slang for thief')
w('تهديد','threat','SAFETY','SUSPICIOUS','noun_infra',
  'tahdid','tahded','tahdid bi l sila7','fi tahdid','3am yi7adid','m7adad bi',
  'A/A/A/A/A/B','تهديد',
  '7=ح in m7adad and 3am yi7adid; tahdid most formal')
w('كلاب ضالة','stray dogs','SAFETY','EXPOSED_HAZARD','noun_person',
  '2lab daliye','2lab m5aliyye','2lab bi l share3','fi 2lab','chien errant','keleb dalyeh',
  'A/A/A/A/B/B','كلاب ضالة',
  '2=ق in 2lab; 5=خ in m5aliyye; chien errant French; keleb = dogs (alt spelling)')
w('حديد بارز','protruding rebar / metal','SAFETY','EXPOSED_HAZARD','noun_infra',
  '7adid bariz','7adid 5arij','7adid 2adem men l ard','7adid mekshouf','7adid tal3an','',
  'A/A/A/A/A','حديد بارز',
  '7=ح in 7adid; 5=خ in 5arij; bariz = protruding; 5arij = sticking out')
w('حفرة بلا إشارة','unmarked hole / danger','SAFETY','EXPOSED_HAZARD','noun_infra',
  '7ofra bla ishara','7afra bla paneau','7ofra mish ma3rouf','7ofra 5atere','7afra ta7diriye','',
  'A/A/B/A/A','حفرة بلا إشارة',
  '7=ح in 7ofra; 5=خ in 5atere; bla = without; ishara = sign')
w('لافتة ساقطة','fallen sign / signboard','SAFETY','EXPOSED_HAZARD','noun_infra',
  'lafta sak3a','lafta saktet','lafita saktet 3al tari2','lawha saktet','paneau seket','',
  'A/A/A/B/B','لافتة ساقطة',
  '3=ع in 3al; saktet/sak3a = fell; paneau French loanword')
w('شخص مصاب','injured person','SAFETY','INJURY','noun_person',
  '7ada 2anje7','7ada waje3','7ada mje7','7ada mjrou7','2anje7','mje7',
  'A/A/B/B/A/B','شخص مصاب',
  '2=ء in 2anje7; 7=ح in 7ada; 2anje7 most Lebanese for injured')
w('شخص فاقد الوعي','unconscious person','SAFETY','INJURY','noun_person',
  '7ada fayed l wa3i','7ada ma3o','7ada 7elo 3al ard','7ada bel ard','7ada mghme 3aleh','',
  'A/B/A/A/A','شخص فاقد الوعي',
  '3=ع in wa3i and 3aleh; 7=ح in 7ada and 7elo; 7ada 7elo 3al ard = lying on ground')
w('مركبة مهجورة','abandoned vehicle','SAFETY','SUSPICIOUS','noun_infra',
  'sayyara mahruke','sayyara mhjoure','sayyara bla masna3a','sayyara mish ma3roufe','','' ,
  'A/A/B/B','مركبة مهجورة',
  'mahruke most Lebanese for abandoned vehicle; mhjoure more formal')
w('إسعاف','ambulance','SAFETY','INJURY','noun_infra',
  'is3af','is3aaf','l is3af','is3aafi','ambulance','ambulans',
  'A/A/A/B/B/B','إسعاف',
  '3=ع required; is3af standard; ambulance French loanword also common')
w('غرق','drowning','SAFETY','INJURY','noun_infra',
  'ghara2','ghre2','7ada 3am yigh2ra2','7ada ghire2','7adese ghara2','',
  'A/B/A/A/A','غرق',
  '2=ق in ghara2; 7=ح in 7ada; 3=ع in 3am; ghara2 most natural')

# ══════════════════════════════════════════════════════════════
# GENERAL CIVIC — EXPANDED
# ══════════════════════════════════════════════════════════════
w('مشكلة','problem','ALL','ALL','noun_civic',
  'mashkle','moshkle','mashetle','mashkleh','l mashkle','fi mashkle',
  'A/B/A/C/A/A','مشكلة',
  'mashkle most common Lebanese; fi mashkle = there is a problem (opener)')
w('حل','solution','ALL','ALL','noun_civic',
  '7ell','7al','7all','ma fi 7ell','la2ou 7ell','bi 7aja la 7ell',
  'A/A/A/A/A/A','حل',
  '7=ح required; 7ell most common; la2ou = found (solution)')
w('شكوى','complaint (noun)','ALL','ALL','noun_civic',
  'shikwe','shekwe','shikwit','l shikwe','shikwe rasmiyi','sawweno shikwe',
  'A/A/B/A/B/A','شكوى',
  'shikwe most natural Lebanese; rasmiyi = official; sawweno = they filed')
w('بلاغ','official report / notification','ALL','ALL','noun_civic',
  'balagh','balaagh','l balagh','balla3','iballa3','tballe3',
  'A/A/A/B/B/B','بلاغ',
  '3=ع in balla3; balagh = formal report; balla3 = to report')
w('تقرير','report (document)','ALL','ALL','noun_civic',
  'ta2rir','ta2reer','ta2rir rasmi','report','taqrir','ta2rir ktabi',
  'A/A/A/B/C/B','تقرير',
  '2=ق in ta2rir; report English loanword also used')
w('متابعة','follow-up','ALL','ALL','noun_civic',
  'mutaba3a','ma fi mutaba3a','la2eina babbe2','msh 3am yitabba3','itabba3na','',
  'A/A/A/A/A','متابعة',
  '3=ع in mutaba3a; babbe2 = slammed door (Lebanese expression for being ignored)')
w('مسؤول','official / responsible person','ALL','ALL','noun_person',
  'mas2oul','mas2oulin','l mas2oul','meen mas2oul','mas2uliyyet meen','l mas2oulin',
  'A/B/A/A/A/B','مسؤول',
  '2=ق in mas2oul; very central word in all Lebanese complaints')
w('موظف','employee / civil servant','ALL','ALL','noun_person',
  'mouwazzaf','mouazzaf','mouwazhzhaf','l mouwazzaf','mouwazzafin','muwazzaf l baladiye',
  'A/A/B/A/B/A','موظف',
  'mouwazzaf most standard; mouwazzafin = plural; l baladiye = municipality')
w('مهندس','engineer','ALL','ALL','noun_person',
  'muhandis','mouhandis','mohandis','l mohandis','mouhandis baladiyi','engenieur',
  'A/A/A/A/A/B','مهندس',
  'mouhandis most common Lebanese; engenieur French loanword also used')
w('فني','technician / repairman','ALL','ALL','noun_person',
  'fanne','feni','l fenne','fanni kahraba','fanni may','technicien',
  'A/B/A/A/A/B','فني',
  'fenne most Lebanese; fanni kahraba = electrician; fanni may = plumber')
w('عامل','worker / laborer','ALL','ALL','noun_person',
  '3amel','3amil','3ummal','l 3amel','she3ghele','3amela',
  'A/A/B/A/B/B','عامل',
  '3=ع required; 3amel most natural; she3ghele = workforce (informal)')
w('مواطن','citizen','ALL','ALL','noun_person',
  'muwaten','muwatinin','nass l 7ayye','l muwaten','muwaten lubneniye','l muwatinin',
  'A/B/A/A/B/B','مواطن',
  '7=ح in 7ayye; muwaten most formal; nass l 7ayye most natural complaint usage')
w('أهالي / مجتمع','community / residents','ALL','ALL','noun_person',
  '2ahali','2ahale','l 2ahali','2ahali l 7ayye','2ahali l mantiqa','l jmaa',
  'A/A/A/A/A/A','أهالي / مجتمع',
  '7=ح in 7ayye; 2=ء in 2ahali; l jmaa = the community (informal)')
w('جمعية','NGO / association','ALL','ALL','noun_civic',
  'jam3iyi','l jam3iyi','jam3iyet','association','ONG','jam3iyit l 7ayye',
  'A/A/A/B/B/A','جمعية',
  '3=ع in jam3iyi; jam3iyi most natural; ONG/association French loanwords')
w('ناشط','activist','ALL','ALL','noun_person',
  'nacht','nachit','nachitiin','militant','activist','nacht madani',
  'A/A/B/B/B/A','ناشط',
  'nacht most natural Lebanese; militant/activist loanwords also used')
w('خدمة عامة','public service','ALL','ALL','noun_civic',
  '5idme 3amme','5idme','l 5idme','5idmet l baladiye','service 3amm','5idme rasmiyi',
  'A/A/A/A/B/B','خدمة عامة',
  '5=خ in 5idme; 3=ع in 3amme; 5idme most natural')
w('فاتورة','bill / invoice','ALL','ALL','noun_civic',
  'fatoura','fatouret','facture','l fatoura','fatoura kahraba','fatoura may',
  'A/A/A/A/A/A','فاتورة',
  'fatoura most Lebanese; facture French loanword; kahraba/may specify type')
w('تعويض','compensation','ALL','ALL','noun_civic',
  'ta3wid','ta3wid 3an','ta3widat','badal','badal 5asara','ta3wid la',
  'A/A/B/A/A/B','تعويض',
  '3=ع required; ta3wid most formal; badal = substitute/compensation')
w('خسارة','loss / damage','ALL','ALL','noun_civic',
  '5sara','5asara','5saret','5aseran','5sara kbire','5asra',
  'A/A/A/B/A/A','خسارة',
  '5=خ required; 5sara most Lebanese contracted form')
w('حق','right / entitlement','ALL','ALL','noun_civic',
  '7a2','7a2na','7a2et','7alna 3ala 7a2','l 7a2','7a2 ta3etna',
  'A/A/B/A/A/A','حق',
  '7=ح and 2=ق both required; 7a2 most common')
w('قانون','law / regulation','ALL','ALL','noun_civic',
  '2anoun','l 2anoun','7asab l 2anoun','2anoune','bi l 2anoun','5alef l 2anoun',
  'A/A/A/A/A/A','قانون',
  '2=ق throughout; 5=خ in 5alef; 7=ح in 7asab; 2anoun most common')
w('مخالفة','violation / infraction','ALL','ALL','noun_civic',
  'mu5alefe','mu5alfit','5alefe','5lefe','infraction','mu5alefet',
  'A/A/A/B/B/A','مخالفة',
  '5=خ in mu5alefe; 5alefe = violation; infraction French loanword')
w('غرامة / جريمة','fine / penalty','ALL','ALL','noun_civic',
  'gharame','ghrama','ghramet','amende','ghrami','',
  'A/A/A/B/A','غرامة',
  'gharame most Lebanese; amende French loanword; no Arabizi markers needed')
w('طلب','request (noun)','ALL','ALL','noun_civic',
  'talab','talabe','l talab','talab rasmi','request','talab ktabi',
  'A/A/A/A/B/B','طلب',
  'talab most natural; request English loanword also used in formal contexts')
w('رقم مرجعي','reference number','ALL','ALL','noun_civic',
  'ra2em marja3i','numero marja3i','numero','l numero','ra2em l shikwe','',
  'A/A/A/A/A','رقم مرجعي',
  '2=ق in ra2em; 3=ع in marja3i; numero French loanword dominant in Lebanese')
w('موعد','appointment / scheduled visit','ALL','ALL','noun_civic',
  'maw3id','maw3id siyane','maw3id baladiyi','3andkon maw3id','sa3a mawa3id','',
  'A/A/A/A/B','موعد',
  '3=ع in maw3id; 3andkon = you have (formal you plural)')
w('معاينة','inspection / assessment visit','ALL','ALL','noun_civic',
  'mo3ayne','mo3aynit','ma3ayni','inspection','mo3aynet maydaniyi','visite terrain',
  'A/A/B/B/A/B','معاينة',
  '3=ع in mo3ayne; maydaniyi = field; visite terrain French loanword')
w('واتساب','WhatsApp (complaint channel)','ALL','ALL','noun_civic',
  'whatsapp','wassap','watsapp','l wassap','3al wassap','wasapp',
  'A/A/A/A/A/B','واتساب',
  '3=ع in 3al; WhatsApp dominant communication channel for Lebanese complaints')
w('تطبيق','mobile application','ALL','ALL','noun_civic',
  'application','app','l app','l application','tatbi2','ttbi2',
  'A/A/A/A/B/C','تطبيق',
  '2=ق in tatbi2; application/app English loanwords dominant')
w('صورة دليل','photo evidence','ALL','ALL','noun_civic',
  'sura dalil','surat l mashkle','sawwarto l mashkle','7attat sura','','' ,
  'A/A/A/A','صورة / دليل',
  '7=ح in 7attat; sura = photo; dalil = evidence')
w('خط ساخن','hotline','ALL','ALL','noun_civic',
  '5att sa5en','5att l shikayat','numero l shikayat','5att l baladiye','ligne directe','',
  'A/A/A/A/B','خط ساخن',
  '5=خ in 5att and sa5en; sa5en = hot')
w('مركز خدمات','service center','ALL','ALL','noun_civic',
  'markez 5idme','markez l baladiye','markez l shikayat','centre de service','l markez','',
  'A/A/A/B/A','مركز خدمات',
  '5=خ in 5idme')

# ══════════════════════════════════════════════════════════════
# LOCATION TYPES (expanded — important for severity escalation)
# ══════════════════════════════════════════════════════════════
w('مدرسة','school','ALL','ALL','noun_location',
  'madrase','l madrase','jemb l madrase','madraset l 7ayye','madrase 7okoumiye','madrase 5asusiyi',
  'A/A/A/A/A/B','مدرسة',
  '7=ح in 7okoumiye and 7ayye; 5=خ in 5asusiyi; proximity = severity escalation trigger')
w('مستشفى','hospital','ALL','ALL','noun_location',
  'mustashfa','l mustashfa','jemb l mustashfa','mustashfet l 7okoume','hopital','',
  'A/A/A/A/B','مستشفى',
  '7=ح in 7okoume; proximity to hospital = severity escalation; hopital French loanword')
w('سوق','market / bazaar','ALL','ALL','noun_location',
  'sou2','souk','l sou2','l sou2 l sha3bi','bazar','merkez',
  'A/A/A/A/B/B','سوق',
  '2=ق in sou2; sha3bi = popular/street market; 3=ع in sha3bi')
w('دكان / محل','shop / store','ALL','ALL','noun_location',
  'dekken','dekkene','ma7all','l dekken','boutique','dukken',
  'A/A/A/A/B/B','دكان / محل',
  '7=ح in ma7all; dekken most natural Lebanese; boutique French loanword')
w('مطعم','restaurant','ALL','ALL','noun_location',
  'mat3am','l mat3am','restaurant','rest','mat3am l 7ayye','',
  'A/A/A/B/A','مطعم',
  '3=ع in mat3am; restaurant French loanword also very common')
w('مسجد / جامع','mosque','ALL','ALL','noun_location',
  'jame3','jeme3','l jame3','jame3 l 7ayye','masjed','msejed',
  'A/A/A/A/C/B','مسجد / جامع',
  '3=ع in jame3; jame3 most Lebanese; masjed more formal')
w('كنيسة','church','ALL','ALL','noun_location',
  'kenise','knise','l kenise','kenisit l 7ayye','eglise','l katetdral',
  'A/B/A/A/A/B','كنيسة',
  '7=ح in 7ayye; eglise French loanword very common')
w('حديقة / متنزه','park / garden / public green space','ALL','ALL','noun_location',
  '7adi2a','l 7adi2a','7adi2et l 7ayye','park','parke','jardin',
  'A/A/A/B/B/B','حديقة',
  '7=ح and 2=ق required; park English; jardin French; both very common in Lebanon')
w('ملعب','playground / sports field','ALL','ALL','noun_location',
  'mal3ab','l mal3ab','mal3ab l 2atfal','terren','terren l 2atfal','terrain',
  'A/A/A/B/B/B','ملعب',
  '3=ع in mal3ab; 2=ق in 2atfal; terren = field (French loanword terrain)')
w('مبنى حكومي / سراي','government building / serail','ALL','ALL','noun_location',
  'saray','l saray','serail','mabne 7okoumi','bnayi 7okoume','moukhatara',
  'A/A/A/A/A/B','مبنى حكومي',
  '7=ح in 7okoumi; serail French loanword; moukhatara = mukhtar\'s office')
w('مركز صحي','health center / clinic','ALL','ALL','noun_location',
  'markez sa77i','markez 7okoumi','dispensaire','l markez','markez tibbi','',
  'A/A/B/A/A','مركز صحي',
  '7=ح in sa77i and 7okoumi; dispensaire French loanword')
w('مخفر / مركز أمن','police station / security post','ALL','ALL','noun_location',
  'ma5far','l ma5far','markez l ISF','markez l shorta','poste','',
  'A/A/A/A/B','مخفر',
  '5=خ in ma5far; poste French loanword')
w('أرض خالية','empty / vacant lot','ALL','ALL','noun_location',
  'l ard l 5ale','l ard l 5alye','l mawdou3 l 5ale','l lot l 5ale','ard 5alye','',
  'A/A/B/C/B','أرض خالية',
  '5=خ in 5ale; common site for illegal dumping and safety issues')
w('مخيم','refugee camp','ALL','ALL','noun_location',
  'mukhayyam','l mukhayyam','l mukhayyam l falastini','l mukhayyam l souri','l camp','',
  'A/A/A/A/B','مخيم',
  '5=خ in mukhayyam; camp French/English loanword; common location in Lebanon')
w('ضاحية','suburb / outskirt','ALL','ALL','noun_location',
  'da7iye','l da7iye','da7yet beirut','da7iye l janubiye','l de7ye','l da7iyi',
  'A/A/A/A/B/A','ضاحية',
  '7=ح in da7iye; da7yet beirut = Beirut southern suburbs; da7iye l janubiye = southern suburb')
w('منطقة صناعية','industrial zone','ALL','ALL','noun_location',
  'mantiqa sina3iye','l zone l sina3iye','l masani3','zone industrie','sina3iye','',
  'A/A/B/B/A','منطقة صناعية',
  '3=ع in sina3iye; masani3 = factories; zone industrielle French loanword')
w('منطقة سكنية','residential area','ALL','ALL','noun_location',
  'mantiqa sakaniyi','mantiqa maskoun fiha','7ayye sakani','zon sakani','','' ,
  'A/A/A/B','منطقة سكنية',
  '7=ح in 7ayye; sakaniyi = residential')

# ══════════════════════════════════════════════════════════════
# PEOPLE (expanded)
# ══════════════════════════════════════════════════════════════
w('ناس','people','ALL','ALL','noun_person',
  'nass','nas','l nass','2ahali','l 2ahali','nass l 7ayye',
  'A/A/A/A/A/A','ناس',
  '7=ح in 7ayye; 2=ء in 2ahali; nass most common Lebanese')
w('ساكنين','residents / inhabitants','ALL','ALL','noun_person',
  'sakinin','sakkinin','sukkaan','l sakinin','sakinin l 7ayye','2ahali l bnayi',
  'A/A/B/A/A/A','ساكنين',
  '7=ح in 7ayye; 2=ء in 2ahali; sakinin most natural Lebanese')
w('أطفال','children','ALL','ALL','noun_person',
  '2atfal','2oulad','wled','awlad','l 2atfal','2atfal l 7ayye',
  'A/A/A/A/A/A','أطفال',
  '2=ء in 2atfal/2oulad; 7=ح in 7ayye; 2atfal most formal; 2oulad/wled most Lebanese spoken')
w('كبار السن','elderly people','ALL','ALL','noun_person',
  'kbar l senn','kbar snin','nas kbar','kbar l 3omer','2ahali kbar','shi5',
  'A/A/A/A/B/B','كبار السن',
  '3=ع in 3omer; shi5 = old man (informal); kbar l senn most respectful')
w('ذوو الاحتياجات الخاصة','people with disabilities','ALL','ALL','noun_person',
  'nass bi 7ajat 5asusiyi','nass mu3a2in','mu3a2in','nass 3andon 3ajz','','' ,
  'A/B/B/C','ذوو الاحتياجات الخاصة',
  '7=ح in 7ajat; 5=خ in 5asusiyi; 3=ع in mu3a2in and 3andon')
w('جيران','neighbors','ALL','ALL','noun_person',
  'jiran','jirani','l jiran','jiraniyye','jiran l 7ayye','l jiraniyye',
  'A/A/A/B/A/A','جيران',
  '7=ح in 7ayye; jiran most natural')
w('مارة / عابرون','passersby','ALL','ALL','noun_person',
  'marre','l marre','3abrin','nass 3am tmarre','3aboriyye','l 3abrin',
  'A/A/B/A/C/B','مارة',
  '3=ع in 3abrin and 3am; marre most natural Lebanese for passersby')
w('ضحية','victim','ALL','ALL','noun_person',
  'da7iye','da7iyit','l da7iye','victime','mutadarrar','mutadarrarin',
  'A/A/A/B/B/B','ضحية',
  '7=ح in da7iye; victime French loanword; mutadarrar = affected person')
w('شاهد','witness','ALL','ALL','noun_person',
  'shahed','l shahed','shuhed','shuhuud','nass shufo','fi shahed',
  'A/A/B/B/A/A','شاهد',
  'shahed most common; shuhed/shuhuud = witnesses plural')

# ══════════════════════════════════════════════════════════════
# VERBS — GENERAL (massive expansion)
# ══════════════════════════════════════════════════════════════
w('يُبلِّغ / يُوصِل','reports / submits complaint','ALL','ALL','verb',
  'yiballa3','nballa3','balla3','yballe3','nsajjel','nwassal',
  'A/A/A/B/A/A','يُبلِّغ / يُوصِّل',
  '3=ع in all forms; yiballa3 most Lebanese for reporting; nsajjel = we register')
w('يطالب','demands / calls for action','ALL','ALL','verb',
  'yittalab','ntaleb','3am yittalab','be2da','ntalbo','talalabna',
  'A/A/A/B/A/B','يطالب',
  '3=ع in 3am; 2=ق in be2da; ntaleb most natural Lebanese')
w('يستجيب / يرد','responds','ALL','ALL','verb',
  'yrud','yrudd','yradde','3am yrud','ma 3am yrud','roddo',
  'A/A/B/A/A/B','يستجيب / يرد',
  '3=ع in 3am; yrud most natural Lebanese')
w('يحل','solves / fixes','ALL','ALL','verb',
  'yi7ill','yi7el','7all','7alo','7allit','la2o 7ell',
  'A/B/A/A/A/A','يحل',
  '7=ح required; 7all most natural noun/verb form')
w('يتدخل','intervenes','ALL','ALL','verb',
  'yitda5al','yitdakhal','3am yitda5al','ma 7ada yitda5al','yitda5alo','',
  'A/B/A/A/A','يتدخل',
  '5=خ in 5al; 3=ع in 3am; 7=ح in 7ada')
w('يُزيل / يشيل','removes / clears away','ALL','ALL','verb',
  'yshil','yshilo','3am yshelou','yji yshil','yshil l zbele','yshil l 7ajez',
  'A/A/A/A/A/A','يُزيل / يشيل',
  '7=ح in 7ajez; 3=ع in 3am; yshil most natural Lebanese for remove/take away')
w('ينظف','cleans / cleans up','ALL','ALL','verb',
  'ynazzef','ykannes','3am ykannes','ykannes l tari2','nazzef l 7ayye','ynazzefo',
  'A/A/A/A/A/A','ينظف',
  '7=ح in 7ayye; 3=ع in 3am; ynazzef most natural')
w('يتصل / يتواصل','contacts / reaches out','ALL','ALL','verb',
  'yitwasal','yitassel','yitassel 3a','3am yitassel','ma fi 7ada yitassel','nballa3',
  'A/A/B/A/A/B','يتواصل',
  '3=ع in 3a and 3am; 7=ح in 7ada; yitassel most natural')
w('يشتكي','complains (verb)','ALL','ALL','verb',
  'yshki','yishki','3am yshki','yshki la','nshki','ishtaka',
  'A/A/A/A/A/C','يشتكي',
  '3=ع in 3am; yshki most natural; ishtaka MSA')
w('ينتظر','waits / waits for action','ALL','ALL','verb',
  'yistanna','yistanne','3am yistanna','yistanna 3al 7all','mestanniyin','mestanye',
  'A/A/A/A/A/B','ينتظر',
  '7=ح in 7all; 3=ع in 3am; yistanna most natural Lebanese; mestanniyin = waiting (plural)')
w('يطلب','requests / asks for','ALL','ALL','verb',
  'ytlob','yitlob','3am ytlob','ytlob men','ntalob','itlabu',
  'A/A/A/A/A/B','يطلب',
  '3=ع in 3am; ytlob most natural; itlabu = they requested')
w('يجيب','brings / fetches','ALL','ALL','verb',
  'yijib','yijibu','yje2','jibu','3am yijib','jibo',
  'A/A/B/A/A/A','يجيب / يُحضر',
  '2=ء in yje2; 3=ع in 3am; yijib most Lebanese')
w('يحفر','digs','ALL','ALL','verb',
  'yi7fur','3am yi7fur','7afrou','yi7fru','7afar','3am ti7fur',
  'A/A/A/A/B/A','يحفر',
  '7=ح required throughout; yi7fur most natural')
w('يردم','fills / backfills hole','ALL','ALL','verb',
  'yirdim','yirdmo','radamo','3am yirdmo','yirdim l 7afra','3am yirdim',
  'A/A/A/A/A/A','يردم',
  '7=ح in 7afra; 3=ع in 3am')
w('يعطل','breaks down / malfunctions','ALL','ALL','verb',
  '3atel','3at al','3am yi3atel','3at alet','3atel byom w byom','3atlet',
  'A/A/A/A/A/A','يعطل',
  '3=ع required throughout; 3atel most common Lebanese for malfunction')
w('يخاف','is scared / fears','ALL','ALL','verb',
  '5ayef','5ayfe','5ayefin','khayyef','3am n5af','l nass 5ayefin',
  'A/A/A/B/A/A','يخاف',
  '5=خ preferred; 3=ع in 3am; 5ayefin = they are scared plural')
w('يُحضِر الشرطة / الإسعاف','calls police / ambulance','ALL','ALL','verb',
  'yijib l shorta','yitassel 3al ISF','yitassel 3al is3af','3am ndawwer 3al is3af','yijib l 2ouat','',
  'A/A/A/A/A','يُحضر الشرطة / الإسعاف',
  '3=ع in 3al and 3am; yijib most natural; 2=ق in 2ouat')
w('يُقيِّم / يُعاين','assesses / inspects','ALL','ALL','verb',
  'yshuf l wad3','yi2adder l mashkle','yji yshuf','y3mel mo3ayne','yi2ayem','',
  'A/A/A/A/B','يُقيِّم / يُعاين',
  '2=ق in yi2adder/yi2ayem; 3=ع in y3mel; yshuf l wad3 most natural')
w('يُبلَّغ / يعرف','is notified / finds out','ALL','ALL','verb',
  'yi3ref','yi3rif','3rif','3alimo','balla3no','3rafna',
  'A/A/A/B/B/A','يُبلَّغ / يعرف',
  '3=ع required; yi3ref most natural Lebanese')
w('يُرمِّم / يُصلِح','repairs / restores','ALL','ALL','verb',
  'ytrammam','yisla7','yi3mel tarmim','tarmamo','ramamo','yis7o7o',
  'A/A/A/A/A/B','يُرمِّم / يُصلِح',
  '7=ح in yisla7; 3=ع in yi3mel; ytrammam most formal')
w('يمنع','prevents / stops','ALL','ALL','verb',
  'yimna3','3am yimna3','mana3ou','ma 7ada yimna3','yimna3on','men3ou',
  'A/A/A/A/A/A','يمنع',
  '3=ع required throughout; yimna3 most natural')
w('يُعلم / يُخبِر','informs / notifies','ALL','ALL','verb',
  'yi3allim','yi5abbar','y5abbar','3am yi5abbar','5abbarno','3allamno',
  'A/A/A/A/A/A','يُعلم / يُخبر',
  '5=خ in yi5abbar; 3=ع in 3am and yi3allim; y5abbar most natural')
w('يتجاوز','passes over / crosses (obstacle)','ALL','ALL','verb',
  'yit3adde','y3adde','3am yi3adde','ma 2adra ti3adde','ma fi tari2 yi3adde','3adde',
  'A/A/A/A/A/B','يتجاوز',
  '3=ع required throughout; 2=ق in 2adra')
w('يُلزِم / يُجبر','forces / compels','ALL','ALL','verb',
  'yilzam','yijbor','ilzamo','3am yilzam','3am yijbro','lazim yilzam',
  'A/A/A/A/A/A','يُلزم / يُجبر',
  '3=ع in 3am; yilzam most natural')
w('يقوم بـ','undertakes / carries out','ALL','ALL','verb',
  'yi2oum bi','yi2oum yshuf','yi2oum yi3mel','2am bi','2amo bi','',
  'A/A/A/B/B','يقوم بـ',
  '2=ق in yi2oum; formal commitment verb')
w('يتسبب','causes / is responsible for','ALL','ALL','verb',
  'tsabab','yitsabab','3am yitsabab','yitsabab bi','hiyye sabab','',
  'A/A/A/A/A','يتسبب',
  '3=ع in 3am; yitsabab most natural Lebanese; sabab = cause')
w('يستغرق / ياخذ وقت','takes time','ALL','ALL','verb',
  'bya5od wa2t','bya5od ktir','3am ya5od wa2t','ma yista7il','msh 3ajile','',
  'A/A/A/A/B','يستغرق وقتاً',
  '5=خ in ya5od; 2=ق in wa2t; 3=ع in 3am; msh 3ajile = not urgent (said sarcastically)')
w('يسجل','registers / records','ALL','ALL','verb',
  'ysajjel','nsajjel','3am nsajjel','sajjelo','sajjel l shikwe','bsajjel',
  'A/A/A/A/A/B','يسجل',
  '3=ع in 3am; nsajjel = we register; ysajjel most natural')

# ══════════════════════════════════════════════════════════════
# ADJECTIVES — EXPANDED
# ══════════════════════════════════════════════════════════════
w('كبير','big / large','ALL','ALL','adjective',
  'kbir','kbire','kbeer','ktir kbir','kebir','kbirr',
  'A/A/B/A/C/C','كبير',
  'kbir universal; -e feminine; kbeer elongated; kbirr emphasis; kebir MSA-influenced')
w('صغير','small / minor','ALL','ALL','adjective',
  'zghir','sgir','sghir','zgheir','zghire','sghire',
  'A/B/A/B/A/B','صغير',
  'zghir most Beiruti; sghir/sgir also common; -e feminine')
w('عميق','deep','ALL','ALL','adjective',
  '3ameq','3ameqe','3amee2','3meeq','3maq','3ame2',
  'A/A/B/B/C/A','عميق',
  '3=ع and 2=ق required; 3ameq most natural; 3amee2 elongated form')
w('قديم','old (thing / object)','ALL','ALL','adjective',
  '2adim','2adime','2adeem','3atiq','3ati2','2dim',
  'A/A/B/A/B/C','قديم',
  '2=ق in 2adim; 3=ع in 3atiq; 3atiq = aged/antiquated (building context)')
w('جديد','new / recent','ALL','ALL','adjective',
  'jdid','jdide','jedid','jedide','jdidanin','ma2tab',
  'A/A/B/B/B/C','جديد',
  'jdid most natural; -e feminine; jdidanin = new ones (plural)')
w('خطير','dangerous','ALL','ALL','adjective',
  '5ater','khater','5atir','5ateer','5ateeer','khateeer',
  'A/B/B/B/C/C','خطير',
  '5=خ preferred; extra letters for emphasis authentic in panic messages')
w('مكشوف','exposed / uncovered','ALL','ALL','adjective',
  'mekshouf','mkshouf','mkshoof','mekshoufe','mekshuf','mkshoof',
  'A/B/B/A/C/C','مكشوف',
  'mekshoufe = feminine form; mekshouf most natural')
w('مكسور','broken','ALL','ALL','adjective',
  'maksour','maksourit','mksour','mksoure','nkassar','ksar',
  'A/B/B/B/A/C','مكسور',
  'maksour standard; nkassar also adj (broken); maksourit = fem/genitive')
w('مسدود','blocked / clogged','ALL','ALL','adjective',
  'masduud','msakkar','msadd','maftoum','msadoud','mashloum',
  'A/B/A/B/C/A','مسدود',
  'masduud standard; mashloum = paralyzed/stuck; maftoum widely used in Lebanon')
w('طافح / فائض','overflowing','ALL','ALL','adjective',
  'tafane','tafanit','mmtele','3am tifout','fay2','tafyaneh',
  'A/A/B/A/B/A','طافح / فائض',
  '2=ق in fay2; tafane most Lebanese; tafanit past-tense form used as adj')
w('غريق / مغمور','flooded / submerged','ALL','ALL','adjective',
  'ghare2','ghre2','2arqa','tafyan','ma2leh may','mghara2',
  'A/B/B/A/A/B','غريق / مغمور',
  '2=ق in ghare2 and 2arqa; 2arqa South Lebanon variant; tafyan most Beiruti')
w('ملوث','contaminated / polluted','ALL','ALL','adjective',
  'mla2wat','mla2wate','wse5','wse5a','lawant','lawanta',
  'A/A/A/A/A/A','ملوث',
  'lawanta Italian loanword very common; wse5/wse5a dirty (5=خ); mla2wate most formal')
w('بايخ / فاسد','rotten / spoiled','ALL','ALL','adjective',
  'bayekh','bayekhe','fased','fasde','bayekh ktir','mtaffes',
  'A/A/A/A/A/B','بايخ / فاسد',
  '5=خ in bayekh; fased = rotten; mtaffes = stinking/putrid')
w('رطب / مبلول','damp / wet','ALL','ALL','adjective',
  'rateb','mbalel','mabloule','mrattab','bli2','rteib',
  'A/A/A/B/B/B','رطب / مبلول',
  'mbalel most natural Lebanese for wet; rateb = damp; 2=ق in bli2')
w('مزعج','annoying / disturbing','ALL','ALL','adjective',
  'mz3ej','miz3ij','maz3ej','miz3ij ktir','m3attel','m3azzel',
  'A/A/B/A/B/B','مزعج',
  '3=ع required; mz3ej most natural Lebanese contracted form')
w('مريح / آمن','safe / comfortable','ALL','ALL','adjective',
  'amen','sali7','mri7','tamem','3adi','mni7',
  'A/A/A/A/A/A','آمن / مريح',
  '7=ح in mri7; 3=ع in 3adi; tamem = fine/OK (Lebanese); mni7 = good/safe')
w('عادي','normal / ordinary','ALL','ALL','adjective',
  '3adi','tabi3i','3adiyye','tabi3i shi','mish 3adi','3adi 3adi',
  'A/A/B/B/A/A','عادي',
  '3=ع required; mish NOT mesh; 3adi 3adi = very normal')
w('ظاهر / واضح','visible / obvious / clear','ALL','ALL','adjective',
  'waze7','wazel','bayan','zaher','3am yinbayin','mbayin',
  'A/A/B/B/A/A','واضح / ظاهر',
  '7=ح in waze7; 3=ع in 3am; waze7 most formal; mbayin most Lebanese casual')
w('مخفي','hidden / concealed','ALL','ALL','adjective',
  'm5abbi','ma5bi','m5abbe','m5abiye','ma7i','5abbi',
  'A/A/B/B/B/C','مخفي',
  '5=خ in m5abbi/ma5bi; 7=ح in ma7i; m5abbi most natural')
w('سريع','fast / quick','ALL','ALL','adjective',
  'sari3','sari3a','sare3','sare3a','bi sor3a','3ajeele',
  'A/A/B/B/A/A','سريع',
  '3=ع in sari3 and 3ajeele')
w('بطيء','slow / delayed (service)','ALL','ALL','adjective',
  'bati2','bate2','bati2 ktir','bati2 jiddan','bate2 shi','msh sari3',
  'A/A/A/B/B/A','بطيء',
  '2=ق in bati2; bati2 ktir = very slow')
w('ثقيل','heavy / serious (problem)','ALL','ALL','adjective',
  't2il','ta2il','t2ile','t2il shi','mashkle t2ile','wad3 t2il',
  'A/A/A/A/A/A','ثقيل',
  '2=ق in t2il; ta2il more formal; used for serious/heavy problems')
w('خفيف','light / minor (issue)','ALL','ALL','adjective',
  '5afif','khafif','5afife','khafife','5afif shi','msh t2il',
  'A/B/A/B/A/A','خفيف',
  '5=خ preferred; -e feminine')
w('قديم التصميم','outdated / old-design infrastructure','ALL','ALL','adjective',
  '2adim','metba2ar','ma3amil 2adime','balayi','blayi','infrastructure 2adime',
  'A/B/B/B/B/B','قديم التصميم',
  '2=ق in 2adim; balayi = worn-out (Lebanese); 3=ع in ma3amil')
w('وسخ / قذر','dirty / filthy','ALL','ALL','adjective',
  'wse5','wse5a','2dher','5anze','5anza','wse5 shi',
  'A/A/B/B/B/A','وسخ / قذر',
  '5=خ in 5anze; 2=ق in 2dher; wse5 most natural Lebanese')
w('نظيف','clean','ALL','ALL','adjective',
  'nzif','nzife','nadif','nadife','nzeef','5ali men nfayat',
  'A/A/B/B/B/A','نظيف',
  '5=خ in 5ali; nzif most natural Lebanese contracted form')

# ══════════════════════════════════════════════════════════════
# SEVERITY MARKERS — EXPANDED
# ══════════════════════════════════════════════════════════════
w('كثير','very / a lot (intensifier)','ALL','ALL','severity_marker',
  'ktir','kter','ktiir','kteer','ktirr','ktirrr',
  'A/B/B/C/C/C','كثير',
  'ktir universal; kter South Lebanon variant; doubled letters = typed emphasis')
w('خطر (noun)','danger (noun)','ALL','ALL','severity_marker',
  '5atar','5tr','khatar','5trrr','5tarrr','5tr ktir',
  'A/B/B/C/C/C','خطر',
  '5=خ preferred; khatar acceptable; 5trrr panic typing — authentic for SAFETY reports')
w('خطير (adj)','dangerous (adjective)','ALL','ALL','severity_marker',
  '5ater','khater','5atir','5ateer','5ateeer','5tr',
  'A/B/B/B/C/B','خطير',
  '5=خ preferred; extra vowels/letters = emphasis; 5tr most compressed form')
w('عاجل','urgent','ALL','ALL','severity_marker',
  '3ajeele','3ajel','3a jal','3ajeeel','3ajjel','3ajill',
  'A/A/B/C/C/C','عاجل',
  '3=ع required; 3ajeele most Lebanese; 3ajjel more formal')
w('فوري','immediate / right now','ALL','ALL','severity_marker',
  'fawri','fawriyi','3ajeele','bi sor3a ktir','bi 7ajet fawriye','halla2 halla2',
  'A/B/A/A/A/A','فوري',
  '7=ح in 7ajet; 3=ع in 3ajeele; fawri most formal; halla2 halla2 = right this instant')
w('لازم / ضروري','must / necessary','ALL','ALL','severity_marker',
  'lazem','darouri','lazim','lazemm','darori','lazem ktir',
  'A/A/B/C/B/A','لازم / ضروري',
  'lazem most natural Lebanese modal; darouri standard')
w('مش منيح','not good / unacceptable','ALL','ALL','severity_marker',
  'mish mnee7','msh mni7','mish mne7','mish 2adem','mish kwayes','msh mne7 abadan',
  'A/A/B/B/B/A','مش منيح',
  '7=ح in mne7; mish ALWAYS — NEVER mesh; abadan = not at all (intensifier)')
w('ما في أمان','unsafe / dangerous situation','ALL','ALL','severity_marker',
  'ma fi aman','mish amen','mish sali7','mish 2amen','5ater','la ma fi aman',
  'A/A/B/B/A/A','ما فيه أمان',
  '5=خ in 5ater; mish NOT mesh')
w('مستعجل','urgent / rushed','ALL','ALL','severity_marker',
  'mista3jel','mista3jlin','3ajeele','3ajle','sari3','yalla 3ajeele',
  'A/A/A/A/B/A','مستعجل',
  '3=ع in mista3jel and 3am; yalla = come on (urgency)')
w('ما يُصدَّق','unbelievable / outrageous','ALL','ALL','severity_marker',
  'ma byetsadda2','ma byt2abbal','shi ma byt2abbal','ma btyit2abbal','shi ma bitawwa3','wallahi',
  'A/A/A/B/B/A','ما يُصدَّق',
  '2=ق in 2abbal; wallahi = I swear (intensifier); intense Lebanese expressions')
w('لا يُحتمَل','unbearable / intolerable','ALL','ALL','severity_marker',
  'ma bt7ammal','ma btyit7ammal','ma fi 7ada yit7ammal','mish 2abel l t7ammul','','',
  'A/A/A/B','لا يُحتمَل',
  '7=ح in 7ammal; 2=ق in 2abel; ma bt7ammal most Lebanese')
w('وضع كارثي','catastrophic situation','ALL','ALL','severity_marker',
  'wad3 karssi','wad3 ta3es','wad3 la2 la2','wad3 bayekh','wad3 mish mni7 abadan','wad3 7arij',
  'A/A/A/A/A/A','وضع كارثي',
  '7=ح in 7arij; la2 la2 = Lebanese expression for very bad; bayekh = rotten/terrible')

# ══════════════════════════════════════════════════════════════
# TIME EXPRESSIONS — EXPANDED
# ══════════════════════════════════════════════════════════════
w('أمس','yesterday','ALL','ALL','time_expr',
  'emes','ams','emsi','l ems','men emes','men ems',
  'A/B/C/C/A/B','أمس',
  'emes most common Lebanese spelling')
w('قبل أمس','day before yesterday','ALL','ALL','time_expr',
  '2abel emes','men 2abel emes','2abl ems','awwel emes','2abl ams','',
  'A/A/B/B/B','قبل أمس',
  '2=ق in 2abel; 2abel emes most natural')
w('اليوم','today','ALL','ALL','time_expr',
  'lyom','l yom','lyoum','hal yom','yom l yom','',
  'A/A/B/B/C','اليوم',
  'lyom most contracted; hal yom = this very day')
w('بكرا','tomorrow','ALL','ALL','time_expr',
  'bokra','bukra','bukre','bkra','ghadan','l yom l jey',
  'A/A/B/B/C/B','غداً / بكرا',
  'bokra most natural Lebanese; ghadan MSA; l yom l jey = the coming day')
w('الآن / هلق','now / right now','ALL','ALL','time_expr',
  'halla2','hala2','hal2','halla','hala','hal2 hal2',
  'A/B/B/C/C/B','الآن / هلأ',
  'halla2 most common; hal2 very contracted; hal2 hal2 = right this instant')
w('حتى الآن','until now / still (no action)','ALL','ALL','time_expr',
  'la halla2','la hal2','la hala2','w la halla2','lessa','lessa ma 3amlo shi',
  'A/B/B/A/B/A','حتى الآن',
  '3=ع in 3amlo; la halla2 most natural; lessa = still/yet; lessa ma = still not')
w('فوراً','immediately','ALL','ALL','time_expr',
  'halla2 halla2','bi sor3a','3ajeele','fawri','7alen','3ajeeeele',
  'A/A/A/A/B/C','فوراً',
  '7=ح in 7alen; 3=ع in 3ajeele; halla2 halla2 = right now right now (emphasis by repetition)')
w('أيام','days','ALL','ALL','time_expr',
  'iyem','ayem','iyam','iyem ktir','2iyem','3 iyem',
  'A/B/B/A/C/A','أيام',
  'iyem most natural Lebanese; 2iyem rare formal; 3 iyem = 3 days (typical complaint duration)')
w('أسبوع / أسبوعين','week / two weeks','ALL','ALL','time_expr',
  '2sbou3','2sbou3een','usbou3','sbou3','men 2sbou3een','2sbou3 kamel',
  'A/A/B/B/A/A','أسبوع / أسبوعان',
  '2=ق; 2sbou3een = two weeks; NEVER "2 sbe3" — use 2sbou3een')
w('شهر / شهرين','month / two months','ALL','ALL','time_expr',
  'sha7r','sha7reen','l sha7r','tlet sha7ur','arba3 sha7ur','sha7r w nus',
  'A/A/A/A/A/A','شهر / شهران',
  '7=ح in sha7r; sha7reen = two months; sha7r w nus = month and a half')
w('سنة','year','ALL','ALL','time_expr',
  'sene','snetein','l sene','tlet snin','snin ktir','men snin',
  'A/A/A/A/A/A','سنة / سنوات',
  'sene most natural; snin = years plural; men snin = for years (typical longstanding complaint)')
w('من زمان','for a long time (complaint framing)','ALL','ALL','time_expr',
  'men zamaan','men zaman','men 2adim','men ktir','men snin','men zamaan w la halla2',
  'A/A/B/B/A/A','منذ زمان',
  '2=ق in 2adim; men zamaan most natural Lebanese; men zamaan w la halla2 = for a long time and still')
w('طول الوقت','all the time / always','ALL','ALL','time_expr',
  'tool l wa2et','toul l wa2t','kell l wa2et','dayman','kell iyem','byom w byom',
  'A/A/A/A/A/A','طوال الوقت',
  '2=ق in wa2et; dayman = always; byom w byom = day after day')
w('في الليل','at night','ALL','ALL','time_expr',
  'bel leil','l leil','bel leylle','bel layl','3al leil','bel leil l madi',
  'A/A/B/B/B/B','في الليل',
  '3=ع in 3al; bel leil most natural; l leil l madi = last night')
w('في الصبح','in the morning','ALL','ALL','time_expr',
  'sob7','l sob7','s-sob7','bel sob7','bel fajr','bel ghdaw',
  'A/A/A/A/B/B','في الصبح',
  '7=ح in sob7; fajr more religious/formal; ghdaw = very early morning (pre-dawn)')
w('كل يوم','every day','ALL','ALL','time_expr',
  'kell yom','kel yom','kell yome','kell ma','byom w byom','kell yom w yom',
  'A/A/B/B/A/A','كل يوم',
  'kell most natural Lebanese; byom w byom = day after day (emphasis)')
w('قريباً','soon (often sarcastically)','ALL','ALL','time_expr',
  '2arib','2areib','men 2arib','2arib inshallah','2arib 2arib','ma 2arib',
  'A/A/A/A/B/A','قريباً',
  '2=ق; inshallah often sarcastic in complaint context; ma 2arib = not soon')
w('إن شاء الله','God willing (also sarcastic)','ALL','ALL','time_expr',
  'inshallah','in sha2 allah','inshallah yisla7','inshallah 2arib','inshalla','nshaallah',
  'A/B/A/A/A/C','إن شاء الله',
  '2=ء in sha2; SARCASTIC usage very common in complaint context for things never done')

# ══════════════════════════════════════════════════════════════
# CONNECTORS — EXPANDED
# ══════════════════════════════════════════════════════════════
w('على','on / at','ALL','ALL','connector',
  '3al','3ala','3al l','3alle','3aleih','3alehon',
  'A/B/A/C/C/C','على',
  '3=ع required; 3al most common contracted Lebanese form')
w('في / بـ','in / at / there is','ALL','ALL','connector',
  'fi','bi','bel','bel l','b-','bbe',
  'A/A/A/B/C/C','في / بـ',
  'fi = in/there-is; bi = in (with proper nouns); bel = in the; fi most common opener')
w('من','from / since','ALL','ALL','connector',
  'men','min','men l','mn','men 3and','men 7add',
  'A/B/A/C/B/B','من',
  '3=ع in men 3and; 7=ح in men 7add; men most common Lebanese')
w('إلى / لـ','to / towards','ALL','ALL','connector',
  'la','3a','3al','la 7add','3a fawq','la ta7t',
  'A/A/A/B/B/B','إلى / لـ',
  '7=ح in 7add; 3=ع in 3a; la most common Lebanese')
w('عند / عنا','at / near / have (possession)','ALL','ALL','connector',
  '3and','3anna','3enna','3andna','3endo','3anda',
  'A/A/A/A/A/A','عند / عندنا',
  '3=ع required in all forms')
w('مع','with','ALL','ALL','connector',
  'ma3','ma3na','ma3kon','wa7do','ma3o','ma3ha',
  'A/A/A/B/B/B','مع',
  '3=ع required; ma3 most common')
w('بدون / بلا','without','ALL','ALL','connector',
  'bdoun','bla','min doun','bidoun','bala','bdoun shi',
  'A/A/B/B/C/A','بدون / بلا',
  'bdoun most natural Lebanese; bla = without (very colloquial); bdoun shi = without anything')
w('حتى','until / even','ALL','ALL','connector',
  '7atta','7ata','7att','la','7ata halla2','7atta la',
  'A/B/C/B/A/B','حتى',
  '7=ح required; 7atta most formal; la halla2 = until now')
w('لأن / لأنو','because','ALL','ALL','connector',
  'la2anno','la2en','3a5er','la2ann','li2anno','la2anno keza',
  'A/B/B/C/B/A','لأن / لأنه',
  '2=ق in la2anno; 5=خ in 3a5er = therefore/so; la2anno most Lebanese')
w('لذلك / لهيك','therefore / so','ALL','ALL','connector',
  'la hayke','la hek','3a5er','men hayke','la hayke bidna','hayke',
  'A/A/B/A/A/B','لذلك / لهيك',
  '5=خ in 3a5er; la hayke most natural Lebanese')
w('لكن / بس','but / however','ALL','ALL','connector',
  'bass','bes','bas','lakin','lakinn','bass ma',
  'A/A/B/B/C/A','لكن / بس',
  'bass most natural Lebanese; lakin MSA-influenced; bass ma = but not')
w('قبل','before','ALL','ALL','connector',
  '2abel','2abl','2abel ma','men 2abel','2abl ma','2abl hek',
  'A/A/A/A/A/A','قبل',
  '2=ق throughout; 2abel most common Lebanese form')
w('بعد','after / still','ALL','ALL','connector',
  'ba3d','ba3d ma','ba3din','ba3dein','men ba3d','ba3d hek',
  'A/A/A/A/A/A','بعد',
  '3=ع required; ba3d most common; ba3d ma = after (conjunction); ba3din = afterwards')
w('إذا / لو','if','ALL','ALL','connector',
  'iza','lo','lw','iza keza','lo kenza','liza',
  'A/A/B/A/B/C','إذا / لو',
  'iza most natural Lebanese; lo = if (hypothetical)')
w('مع ذلك / بالرغم','nevertheless / despite','ALL','ALL','connector',
  'ma3 hek','ma3 hayke','bil rghem','ma3 kell hek','','' ,
  'A/A/B/A','مع ذلك / بالرغم',
  '3=ع in ma3; bil rghem = despite; ma3 kell hek = despite all this')
w('أيضاً / كمان','also / too','ALL','ALL','connector',
  'kamen','kman','aydan','kamen 7ada','w kamen','ba3do kamen',
  'A/A/B/A/A/A','أيضاً / كمان',
  '7=ح in 7ada; kamen most natural Lebanese; aydan MSA')

# ══════════════════════════════════════════════════════════════
# SENSORY / QUALITY / STATE WORDS
# ══════════════════════════════════════════════════════════════
w('رائحة كريهة','foul / bad smell','ALL','ALL','noun_infra',
  'ri7a mish mnee7a','ri7a bayse','ri7a keri7a','ri7et ta3affun','ri7a 5anza','ri7a ma btit7ammal',
  'A/A/B/A/B/A','رائحة كريهة',
  '7=ح in ri7a and 7ammal; mish NEVER mesh; 5=خ in 5anza; ta3affun = decomposition (3=ع twice)')
w('ضجيج','noise / racket','ALL','ALL','noun_infra',
  'dajje','dajje ktir','gawghaw','sawt 3ali','3ajaj','fi sawt mish mni7',
  'A/A/B/A/B/A','ضجيج',
  '3=ع in 3ali and 3ajaj; dajje most Lebanese for noise/racket')
w('صوت غريب','strange noise / sound','ALL','ALL','noun_infra',
  'sawt gharib','sawt mish 3adi','sawt kbir','fi sawt','sawt 5arb','sawt mish tabi3i',
  'A/A/A/A/A/B','صوت غريب',
  '3=ع in 3adi; 5=خ in 5arb; mish NOT mesh')
w('ظلام / عتمة','darkness / blackout','ALL','ALL','noun_infra',
  '3atme','dalma','zalma','zalme','3etme','3atmet share3',
  'A/A/B/B/B/A','ظلام / عتمة',
  '3=ع in 3atme; dalma South Lebanon; zalma Bekaa/South; 3atmet share3 = dark street')
w('وسخ','dirty (state)','ALL','ALL','adjective',
  'wse5','wse5a','2dher','5anze','5anza','mesekhin',
  'A/A/B/B/B/B','وسخ',
  '5=خ in 5anze/5anza; 2=ق in 2dher; wse5 most natural Lebanese')
w('نظيف','clean (state)','ALL','ALL','adjective',
  'nzif','nzife','nadif','nadife','nzeef','5ali men nfayat',
  'A/A/B/B/B/A','نظيف',
  '5=خ in 5ali; nzif most natural Lebanese contracted form')
w('حار','hot (temperature)','ALL','ALL','adjective',
  '7ar','7arre','7arin','7ar ktir','7arr','7arrr',
  'A/A/B/A/C/C','حار',
  '7=ح required; 7ar most common; 7arr/7arrr emphasis forms')
w('بارد','cold (temperature)','ALL','ALL','adjective',
  'bared','barde','barid','barid ktir','bared ktir','2ardes',
  'A/A/B/A/A/C','بارد',
  '2=ق in 2ardes (very cold, Bekaa); bared most natural Lebanese; -e feminine')
w('رطب','humid / damp','ALL','ALL','adjective',
  'rateb','rati','rtibi','fi rutube','rateb ktir','',
  'A/A/B/B/A','رطب',
  'rateb most natural; rutube = humidity; common in basement/wall seepage complaints')
w('ثقيل','heavy / oppressive (smell/situation)','ALL','ALL','adjective',
  't2il','ta2il','t2il shi','mashkle t2ile','wad3 t2il','t2il ktir',
  'A/A/A/A/A/A','ثقيل',
  '2=ق in t2il; t2il ktir = very heavy/serious')

# ══════════════════════════════════════════════════════════════
# LEBANESE-SPECIFIC TERMS
# ══════════════════════════════════════════════════════════════
w('أمبيرجي','private generator operator','ELECTRICITY','ALL','noun_person',
  'amperjiye','amperjiyye','sa7eb l moualid','sa7ab l walid','sa7eb l generator','',
  'A/A/A/A/A','أمبيرجي',
  'UNIQUE LEBANESE: private generator operator; sa7eb = owner; amperjiye most natural term')
w('قطع الدولة','state power hours (rationed)','ELECTRICITY','ALL','noun_infra',
  '2ata3 l dawle','saet l dawle','kahrabet l dawle','sa3et l EDL','2ata3 EDL','3atmet l dawle',
  'A/A/A/A/A/A','قطع الدولة',
  '2=ق in 2ata3; 3=ع in 3atmet; UNIQUE LEBANESE: people track state power hours per zone')
w('جدول الإمبير','generator schedule','ELECTRICITY','ALL','noun_infra',
  'jadwal l amper','jadwal l walid','jadwal l moualid','maw3id l moualid','jadwal l generator','',
  'A/A/A/B/B','جدول الأمبير',
  '3=ع in maw3id; UNIQUE LEBANESE: generator schedule shared per building/street')
w('ساعات الكهرباء','electricity hours (rationed)','ELECTRICITY','ALL','noun_infra',
  'sa3et l kahraba','sa3et l EDL','kam sa3a 3andkon','sa3et l dawle','sa3et l moualid','kam sa3a baykon',
  'A/A/A/A/A/A','ساعات الكهرباء',
  '3=ع in 3andkon/baykon; kam sa3a = how many hours — the classic Lebanese question')
w('بطارية / طاقة شمسية','battery / solar power','ELECTRICITY','ALL','noun_infra',
  'battariye','l battariye','solar','solar panel','ta2a shamsiye','UPS',
  'A/A/A/A/B/B','بطارية / طاقة شمسية',
  '2=ق in ta2a; solar/solar panel English loanwords very common; UPS for inverter')
w('ساعات المياه','water hours (rationed supply)','WATER','ALL','noun_infra',
  'sa3et l may','maw3id l may','yom l may','sa3et l may ta3 l 7ayye','may ema ma ji','',
  'A/A/A/A/B','ساعات المياه',
  '7=ح in 7ayye; UNIQUE LEBANESE: water supply rationed by hours/days per neighborhood')
w('تانكر مياه','water delivery tanker','WATER','ALL','noun_infra',
  'tanker','tankar','l tanker','tanker may','sa7riij','tanker BMLWE',
  'A/A/A/A/B/A','صهريج / تانكر',
  'tanker English loanword dominant; sa7riij formal Arabic; BMLWE tankers = government delivery')
w('مولد بالمشترك','shared building/street generator','ELECTRICITY','ALL','noun_infra',
  'moualid mshterak','walid mshterak','kahraba mshtarake','l mshterak','generator mshterak','',
  'A/A/A/B/A','مولد مشترك',
  'mshterak = shared; UNIQUE LEBANESE: building or street shares one generator subscription')
w('واسطة','wasta — connections / nepotism','ALL','ALL','noun_civic',
  'waste','wastet','fi waste','baddna waste','bi l waste','waste lazmit',
  'A/A/A/A/A/A','واسطة',
  'UNIQUE LEBANESE: wasta = using connections/nepotism to get things done; extremely common in complaints about unequal service')
w('طائفية خدمات','sectarian service distribution','ALL','ALL','noun_civic',
  '7ayye ta3 l 7ezb','ta2ifiye bi l 5idme','mish 3adel','7ayye l flen a7san','ta2ifiye','',
  'A/B/A/A/B','طائفية خدمات',
  '7=ح in 7ayye; 5=خ in 5idme; ta2ifiye = sectarianism; UNIQUE LEBANESE context')

# ══════════════════════════════════════════════════════════════
# COMPLAINT FRAMING — EXPANDED
# ══════════════════════════════════════════════════════════════
w('في مشكلة','there is a problem (opener)','ALL','ALL','complaint_phrase',
  'fi mashkle','fi mashetle','fi moshkle','3enna mashkle','3andna mashkle','fi shi',
  'A/A/B/A/A/B','في مشكلة',
  '3=ع in 3enna; fi most natural opener for Lebanese complaints')
w('بدنا نشكي','we want to complain','ALL','ALL','complaint_phrase',
  'bedna nshki','baddna nshki','bedna nshki 3an','badna nsajjel shikwe','bedna nballa3','baddna n3arref',
  'A/A/A/B/A/A','بدنا نشكي',
  '3=ع in 3an and n3arref; 3=ع in nballa3; bedna most natural Lebanese opener')
w('كيف نوصل','how to report this','ALL','ALL','complaint_phrase',
  'keef nwassal','keef nsajjel','keef nballa3','keef n3arref','meen nkallim','meen yji',
  'A/A/A/B/A/A','كيف نوصل',
  '3=ع in n3arref; 7=ح in nkallim; meen = who')
w('لمين المسؤولية','whose responsibility is this','ALL','ALL','complaint_phrase',
  'mas2uliyyet meen','ta2 meen l mas2uliyet','meen mas2oul','meen byi3mel','meen l mas2oul 3ala hek','',
  'A/A/A/A/A','لمين المسؤولية',
  '2=ق in mas2uliyyet; 3=ع in byi3mel and 3ala; meen = who')
w('ممكن حدا يجي','can someone please come','ALL','ALL','complaint_phrase',
  'mumkin 7ada yji','mumkin yji 7ada','mumkin 7ada yiji yshuf','mumkin shirke tinzal','yiji 7ada','yalla yji 7ada',
  'A/A/A/A/B/A','ممكن حدا يجي',
  '7=ح in 7ada; mumkin = can/possible (polite request); yalla = urgency marker')
w('ما عم يردوا','they are not responding','ALL','ALL','complaint_phrase',
  'ma 3am yrudou','ma 7ada 3am yrud','ma 3am yrod','msh 3am yrudou','ma fi 7ada yrud','ma rddo',
  'A/A/A/B/A/A','ما عم يردوا',
  '3=ع in 3am; 7=ح in 7ada; very common complaint about authorities ignoring reports')
w('من زمان وما في حل','for a long time with no solution','ALL','ALL','complaint_phrase',
  'men zamaan w ma fi 7ell','men mdde w ma 7ada 3amel shi','la halla2 ma fi 7ell','men snin w la 7ell','men zamaan w msh 3am yi7ello','',
  'A/A/A/A/A','من زمان وما في حل',
  '7=ح in 7ell and 7ada; 3=ع in 3amel and 3am; the most common Lebanese complaint framing')
w('الناس خايفين','people are scared / worried','ALL','ALL','complaint_phrase',
  'l nass khayfin','l nass 2al2anin','l sakinin khayfin','l 2ahali 5ayefin','khelna khayfin','l nass 5ayfa',
  'A/A/A/A/A/A','الناس خايفين',
  '5=خ in 5ayefin; 2=ق in 2al2anin; khelna = we are scared too (inclusive)')
w('يلا / بسرعة','come on / hurry up','ALL','ALL','complaint_phrase',
  'yalla','yala','yalla yalla','yalla 3ajeele','yalla sari3','yalla 7alle',
  'A/A/A/A/A/A','يلا / بسرعة',
  '3=ع in 3ajeele; 7=ح in 7alle; yalla is a universal Lebanese urgency marker in all complaint contexts')
w('والله ما في حدا','I swear there is nobody (helping)','ALL','ALL','complaint_phrase',
  'walla ma fi 7ada','ma fi 7ada y7ke ma3na','ma 7ada 3am yishma3na','walla ma fi 7ell','ma fi shi byisir','',
  'A/A/A/A/A','والله ما في حدا',
  '7=ح in 7ada and y7ke; 3=ع in ma3na and 3am; walla = I swear (common filler/intensifier)')
w('شو هاد البلد','what kind of country is this','ALL','ALL','complaint_phrase',
  'shu hal balad','shu ha l wad3','shu hal dawle','shu hal shi','shu l bala2 ha','',
  'A/A/A/A/B','شو هاد البلد',
  '2=ء in bala2; very common Lebanese expression of frustration with state services')
w('شكراً مقدماً','thank you in advance','ALL','ALL','complaint_phrase',
  'shukran mu2addaman','shukran men 2abel','merci mu2addaman','merci la2addam','ya3tikon l 3afye','',
  'A/B/A/B/A','شكراً مقدماً',
  '2=ق in mu2addaman; merci French loanword; ya3tikon l 3afye = may God give you strength (most Lebanese closing)')
w('أرجوكم / من فضلكم','please (polite formal request)','ALL','ALL','complaint_phrase',
  '2arjoukon','rjoukon','min fadlkon','men fadlkon','2arjoukun','raja2an',
  'A/B/A/A/B/C','أرجوكم / من فضلكم',
  '2=ء in 2arjoukon; 2arjoukon most Lebanese polite form; raja2an MSA')
w('إن شاء الله يُحل','hopefully it gets solved (hopeful or sarcastic)','ALL','ALL','complaint_phrase',
  'inshallah yisla7','inshallah yi7ill','inshallah 2arib','inshallah lama ma bkoun','inshallah yom ma bkoun 7ayet','',
  'A/A/A/B/C','إن شاء الله يحل',
  '7=ح in yi7ill; 2=ق in 2arib; last two variants are sarcastic (inshallah when I\'m long gone); very Lebanese')

# ══════════════════════════════════════════════════════════════
# INSTITUTIONS (consolidated, with all variants)
# ══════════════════════════════════════════════════════════════
w('بلدية','municipality (general)','ALL','ALL','institution',
  'baladiye','l baladiye','baladiyit l 7ayye','l belediyi','baladiyye','l baladiye ta3 l 7ayye',
  'A/A/A/B/C/A','بلدية',
  '7=ح in 7ayye; baladiye most common; l belediyi more contracted')
w('مخترية','mukhtar\'s office (local chief)','ALL','ALL','institution',
  'moukhatara','l moukhatara','3end l mou5tar','l mu5tar','3end l mu5tar','',
  'A/A/A/A/A','مختارية',
  '5=خ in mu5tar; mou5tar = mukhtar; local community leader; often first contact for complaints in Lebanon')
w('CDR','Council for Dev & Reconstruction','ROADS','ALL','institution',
  'CDR','l CDR','majlis l inma2','conseil du développement','l ashghal l CDR','CDR lebnen',
  'A/A/B/B/B/A','مجلس الإنماء والإعمار',
  '2=ق in inma2; CDR most common acronym')
w('EDL','Electricité du Liban','ELECTRICITY','ALL','institution',
  'EDL','kahrabet l dawle','kahrabet lebnen','shirket l kahraba','l EDL','kahraba EDL',
  'A/A/A/B/A/A','كهرباء لبنان',
  'EDL widely recognized acronym for Lebanese electricity company')
w('BMLWE','Beirut & Mount Lebanon Water','WATER','ALL','institution',
  'BMLWE','mu2asaset l may','may bayrut','may jbel lebnen','l mu2assase','BMLWE beirut',
  'A/B/B/C/C/A','مؤسسة مياه بيروت وجبل لبنان',
  '2=ء in mu2asaset; Beirut and Mount Lebanon districts only; BMLWE most common reference')
w('NLWE','North Lebanon Water Establishment','WATER','ALL','institution',
  'NLWE','may lebnen l shimali','may l shemal','may libnen l shimali','mu2asaset may l shemal','',
  'A/B/B/C/C','مؤسسة مياه لبنان الشمالي',
  'North Lebanon and Akkar districts')
w('SLWE','South Lebanon Water Establishment','WATER','ALL','institution',
  'SLWE','may lebnen l jnoubi','may l jnoub','may libnen l jnoubi','mu2asaset may l jnoub','',
  'A/B/B/C/C','مؤسسة مياه لبنان الجنوبي',
  'South Lebanon and Nabatieh districts')
w('BWE','Bekaa Water Establishment','WATER','ALL','institution',
  'BWE','may l be2a2','may l beqa3','may l be2a','may l bekaa','mu2asaset may l be2a2',
  'A/B/B/C/C/C','مؤسسة مياه البقاع',
  '2=ق in be2a2; Bekaa and Baalbek-Hermel districts')
w('MOE','Ministry of Environment','WASTE','ALL','institution',
  'MOE','wezaret l bi2a','wezaret l biye','wezaret l biya','l wezara l bi2a','l bi2a',
  'A/B/C/C/B/B','وزارة البيئة',
  '2=ء in bi2a; MOE for illegal dumping and burning waste')
w('ISF','Internal Security Forces','SAFETY','ALL','institution',
  'ISF','l shorta','2ouat l amn','l shurta','l 2ouat','darrak',
  'A/A/A/B/B/C','قوى الأمن الداخلي',
  '2=ق in 2ouat; darrak = gendarmerie (rural Lebanon)')
w('CD','Civil Defense (Défense Civile)','SAFETY','ALL','institution',
  'CD','l CD','difa3 madani','l difa3','défense civile','l difa3 l madani',
  'A/A/A/A/B/A','الدفاع المدني',
  '3=ع in difa3; CD most used acronym; défense civile French name')
w('MPWT','Ministry of Public Works & Transport','ROADS','ALL','institution',
  'MPWT','wezaret l ashghal','l ashghal l 3amma','l wezara l 3amma','wezaret l nakel','l ashghal',
  'A/B/B/B/B/A','وزارة الأشغال العامة',
  '3=ع in 3amma and ashghal; l ashghal most commonly used shorthand')
w('شركة خاصة للكهرباء','private electricity company','ELECTRICITY','ALL','institution',
  'shirket kahraba 5asusiyi','l shirke l 5asusiyi','shirket kahraba','l shirke','5asusiyi','',
  'A/A/A/B/B','شركة خاصة للكهرباء',
  '5=خ in 5asusiyi')
w('حزب سياسي / تيار','political party (controls local services)','ALL','ALL','institution',
  '7ezb','l 7ezb','tiyer siyesi','tiyer','l tiyer','l mas2oulin ta3 l 7ezb',
  'A/A/B/B/B/A','حزب / تيار سياسي',
  '7=ح in 7ezb; in Lebanon parties often control local utilities — relevant in routing')
w('وزارة الصحة','Ministry of Health','SAFETY','ALL','institution',
  'wezaret l si77a','l si77a','MS','ministere de la sante','wezaret si77a','',
  'A/A/B/B/A','وزارة الصحة',
  '7=ح in si77a; relevant for medical waste and public health issues')

# ── Final validation ──────────────────────────────────────────
print(f"New rows: {len(rows)}")
bad_mesh = []
for r in rows:
    for cell in r[5:11]:
        if re.search(r'\bmesh\b', cell):
            bad_mesh.append((r[0], cell))
missing_v1 = [r for r in rows if not r[5]]
print(f"mesh errors: {len(bad_mesh)}")
if bad_mesh:
    for x in bad_mesh: print(f"  MESH: {x}")
print(f"missing v1: {len(missing_v1)}")

cols = ['arabic_script','english','sector','issue_type','category',
        'v1','v2','v3','v4','v5','v6','tiers','normalization','usage_note']

import os as _os
_os.makedirs('data/knowledge_base/arabizi', exist_ok=True)
_out_path = 'data/knowledge_base/arabizi/bfl_raw_output.csv'
with open(_out_path, 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.writer(f, quoting=csv.QUOTE_ALL)
    writer.writerow(cols)
    writer.writerows(rows)

print(f"Written to {_out_path}")
