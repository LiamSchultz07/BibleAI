"""Passages where Christian traditions genuinely and durably disagree.

Why this exists
---------------
An assistant that answers "what does this passage mean?" from a single
interpretive tradition, without saying so, is not neutral — it is partisan
while sounding authoritative. That is the most damaging failure mode a Bible
AI has, and no amount of general prompt language reliably prevents it, because
the model does not know *which* passages are contested unless it is told.

So contested ground is treated as data, not vibes. When retrieval lands inside
one of these spans, the assistant is required to surface the disagreement and
attribute each reading to the tradition that holds it.

Editorial standard for entries
------------------------------
Each position is written the way a thoughtful adherent of that tradition would
put it, using their own reasoning and emphases. Positions are not ranked, and
no entry names a winner. Where a tradition's view has internal variety, the
entry says so rather than flattening it.

`ref` strings are resolved to verse spans at ingest time by the reference
parser, so they can be written the way a person would cite them.
"""

from __future__ import annotations

CONTESTED: list[dict] = [
    {
        "ref": "Genesis 1:1-2:3",
        "topic": "Creation and the days of Genesis",
        "question": "Are the six days of creation ordinary days, long ages, or a literary structure?",
        "positions": {
            "Young-earth creationist": "The days are ordinary 24-hour days, and the genealogies imply a comparatively recent creation. The repeated 'evening and morning' formula is read as deliberately marking normal days.",
            "Old-earth / day-age": "The Hebrew *yom* can denote an extended period, and the seventh day has no closing formula, suggesting the days are epochs rather than 24-hour units.",
            "Framework / literary": "The six days form a poetic structure — days 1-3 establish realms, days 4-6 fill them — making the chapter a theological ordering of creation rather than a chronological report.",
            "Evolutionary creation": "Genesis addresses who creates and why, using the cosmology of its original audience; the mechanism of creation is a scientific question the text does not intend to settle.",
            "Eastern Orthodox": "The Fathers read the account both literally and allegorically without treating the choice as decisive for faith; the emphasis falls on God as uncreated Creator.",
        },
    },
    {
        "ref": "Genesis 3:1-24",
        "topic": "The fall and its consequences",
        "question": "What exactly was transmitted to humanity through Adam's sin?",
        "positions": {
            "Augustinian / Western": "Guilt as well as corruption is inherited; humanity is born already culpable and unable to turn to God without prevenient grace.",
            "Eastern Orthodox": "What is inherited is mortality and a corrupted inclination — 'ancestral sin' — but not personal guilt for Adam's act.",
            "Pelagian and semi-Pelagian (historically contested)": "Adam's sin is primarily a bad example; each person sins by imitation. Condemned at Carthage and Orange, but the debate shaped all later positions.",
        },
    },
    {
        "ref": "Exodus 20:4-6",
        "topic": "Images and their veneration",
        "question": "Does the second commandment prohibit religious images entirely?",
        "positions": {
            "Eastern Orthodox": "The prohibition targets idols of false gods. Because God took on visible flesh in Christ, depicting him is a confession of the Incarnation; veneration passes to the prototype, and is distinct from worship.",
            "Roman Catholic": "Substantially the same reasoning, formalized at Nicaea II, distinguishing *latria* (worship, God alone) from *dulia* (honor given to saints and images).",
            "Reformed": "The commandment forbids making images for religious use at all; worship is regulated strictly by what Scripture positively commands.",
            "Lutheran and Anglican": "Images are permissible as teaching aids and adornment but must not receive veneration.",
        },
    },
    {
        "ref": "Malachi 3:8-12",
        "topic": "Tithing",
        "question": "Does the tithe bind Christians?",
        "positions": {
            "Tithe as binding": "The tithe predates the Mosaic law in Abraham and Jacob, so it reflects an enduring principle rather than a repealed ceremonial statute.",
            "Grace giving": "The New Testament never repeats the tithe command for the church; 2 Corinthians 8-9 teaches proportional, cheerful, voluntary giving instead.",
            "Covenantal reading": "The passage addresses Israel under a specific covenant with specific blessings and curses, and applying its promises directly to individual finances misreads its audience.",
        },
    },
    {
        "ref": "Isaiah 7:14",
        "topic": "The Immanuel prophecy",
        "question": "Does *almah* mean 'virgin', and does the prophecy concern Jesus?",
        "positions": {
            "Traditional Christian": "The Septuagint rendered *almah* as *parthenos* (virgin) well before Christ, and Matthew 1:23 identifies the fulfillment in Jesus.",
            "Dual fulfillment": "The sign had an immediate eighth-century referent in Ahaz's day and a fuller messianic fulfillment later — a pattern common in prophetic literature.",
            "Historical-critical": "*Almah* means a young woman of marriageable age; the sign concerned a child born in Isaiah's own time as a timetable for Judah's deliverance.",
            "Jewish interpretation": "The passage speaks of a child in Isaiah's era and is not messianic; Christian readings depend on the Greek rather than the Hebrew.",
        },
    },
    {
        "ref": "Isaiah 53:1-12",
        "topic": "The identity of the Suffering Servant",
        "question": "Who is the servant who suffers?",
        "positions": {
            "Christian": "The servant is the Messiah, and the New Testament reads the chapter as fulfilled in Jesus' death (Acts 8:32-35, 1 Peter 2:22-25).",
            "Jewish interpretation": "The servant is corporate Israel, suffering among the nations — a reading supported by explicit servant identifications elsewhere in Isaiah (41:8, 49:3).",
            "Historical-critical": "The figure may be the prophet, a righteous remnant, or an idealized individual; the text does not resolve it.",
        },
    },
    {
        "ref": "Matthew 5:38-48",
        "topic": "Nonviolence and enemy love",
        "question": "Does Jesus forbid all use of force?",
        "positions": {
            "Anabaptist / historic peace churches": "The command is a direct rule for disciples: Christians renounce violence entirely, including in war and self-defense.",
            "Just war tradition": "Jesus addresses personal retaliation and private vengeance, not the state's God-given responsibility to restrain evil (Romans 13:1-4).",
            "Lutheran two-kingdoms": "The Christian is bound to nonresistance personally while still serving legitimately in offices that bear the sword.",
            "Idealist / eschatological": "The Sermon depicts the ethics of the coming kingdom, exposing the depth of human need rather than legislating current policy.",
        },
    },
    {
        "ref": "Matthew 16:18-19",
        "topic": "The rock, the keys, and church authority",
        "question": "What is 'this rock', and what authority do the keys confer?",
        "positions": {
            "Roman Catholic": "Peter himself is the rock, and the keys establish a teaching and governing office that continues in his successors, the bishops of Rome.",
            "Eastern Orthodox": "Peter holds a real primacy of honor, but the keys are given to the apostolic college as a whole; authority resides in the conciliar episcopate, not one see.",
            "Reformed and Baptist": "The rock is Peter's confession of Christ, or Peter as the first confessor; the keys are the church's ministry of proclaiming forgiveness through the gospel.",
            "Lutheran": "The keys belong to the whole church and are exercised through the preaching of the word and absolution, not through a papal office.",
        },
    },
    {
        "ref": "Matthew 19:3-12",
        "topic": "Divorce and remarriage",
        "question": "Is marriage dissoluble, and may the divorced remarry?",
        "positions": {
            "Roman Catholic": "A consummated sacramental marriage is indissoluble; the 'exception clause' concerns unlawful unions. Annulment declares a marriage was never validly contracted.",
            "Eastern Orthodox": "Marriage is ideally indissoluble, but the church may permit remarriage after divorce by *oikonomia* — pastoral accommodation to human weakness.",
            "Protestant (majority)": "The exception for *porneia*, together with 1 Corinthians 7:15, permits divorce and remarriage in cases of adultery or desertion.",
            "No-remarriage view": "Divorce may sometimes be permitted, but remarriage while a former spouse lives constitutes adultery.",
        },
    },
    {
        "ref": "Matthew 24:1-51",
        "topic": "The Olivet Discourse",
        "question": "Do these predictions describe AD 70, the end of history, or both?",
        "positions": {
            "Preterist": "The discourse was fulfilled in the destruction of Jerusalem in AD 70, which 'this generation shall not pass' requires.",
            "Futurist": "The events describe a still-future tribulation immediately preceding Christ's return.",
            "Historicist": "The discourse maps the whole span of church history in sequence.",
            "Idealist": "It portrays recurring patterns of persecution and vindication rather than a datable sequence.",
            "Mixed / dual-horizon": "AD 70 genuinely fulfilled part of the prophecy while prefiguring a final consummation — the most common view among modern commentators.",
        },
    },
    {
        "ref": "Matthew 26:26-29",
        "topic": "The words of institution",
        "question": "In what sense is the bread Christ's body?",
        "positions": {
            "Roman Catholic": "Transubstantiation: the substance of bread and wine becomes Christ's body and blood while the appearances remain.",
            "Eastern Orthodox": "The elements truly become Christ's body and blood; the change is affirmed as real but deliberately left a mystery rather than explained philosophically.",
            "Lutheran": "Sacramental union: Christ's body and blood are truly present 'in, with, and under' bread and wine that remain bread and wine.",
            "Reformed": "Christ is truly but spiritually present, received by faith through the Spirit; the elements are signs that genuinely convey what they signify.",
            "Baptist / Zwinglian": "The supper is a memorial and proclamation; 'this is my body' is figurative, as in 'I am the door'.",
        },
    },
    {
        "ref": "Mark 16:9-20",
        "topic": "The longer ending of Mark",
        "question": "Is this passage part of the original Gospel?",
        "positions": {
            "Critical text scholarship": "The longer ending is absent from the earliest and best manuscripts (Sinaiticus, Vaticanus) and differs in vocabulary and style; most modern translations mark it.",
            "Majority / Byzantine text": "The ending appears in the overwhelming majority of manuscripts and in early patristic citation, and should be retained.",
            "Received text (KJV tradition)": "The passage is canonical Scripture, and its removal reflects flawed critical presuppositions.",
        },
    },
    {
        "ref": "John 3:1-8",
        "topic": "Born of water and the Spirit",
        "question": "What is the 'water' of new birth?",
        "positions": {
            "Sacramental (Catholic, Orthodox, Lutheran, Anglican)": "Water refers to baptism, through which regeneration is effected.",
            "Natural birth": "Water denotes physical birth, contrasted with spiritual birth — 'born of water' and 'born of flesh' in parallel.",
            "Word and Spirit": "Water symbolizes cleansing by the word (Ephesians 5:26, Titus 3:5) rather than the rite itself.",
            "Ezekiel allusion": "The phrase echoes Ezekiel 36:25-27, where water and Spirit together describe eschatological cleansing and renewal.",
        },
    },
    {
        "ref": "John 6:47-59",
        "topic": "Eating the flesh of the Son of Man",
        "question": "Is this discourse eucharistic or metaphorical?",
        "positions": {
            "Roman Catholic and Orthodox": "The discourse is eucharistic; the shift to graphic 'chew' language and Jesus' refusal to soften it when disciples leave indicate literal intent.",
            "Reformed": "The chapter is about believing in Christ — verse 47 makes faith the operative term — though it illuminates what the supper conveys.",
            "Baptist / memorialist": "The language is entirely metaphorical for faith; verse 63, 'the flesh profits nothing', is decisive.",
            "Lutheran": "Primarily about faith, but consistent with the real presence taught in the institution narratives.",
        },
    },
    {
        "ref": "Acts 2:38",
        "topic": "Baptism and the forgiveness of sins",
        "question": "Is baptism instrumental in receiving forgiveness?",
        "positions": {
            "Baptismal regeneration (Catholic, Orthodox, Lutheran, Churches of Christ)": "Baptism is the God-appointed means through which forgiveness and the Spirit are given.",
            "Baptist / Reformed": "Baptism is the sign and seal of a forgiveness already received by faith; the Greek *eis* can mean 'with reference to' rather than 'in order to obtain'.",
            "Pentecostal": "Forgiveness comes through repentance and faith, with Spirit baptism as a distinct subsequent experience.",
        },
    },
    {
        "ref": "Romans 5:12-21",
        "topic": "Original sin and imputation",
        "question": "How does Adam's sin affect his descendants?",
        "positions": {
            "Reformed / Augustinian": "Adam's guilt is imputed to all humanity by federal representation, paralleling the imputation of Christ's righteousness.",
            "Eastern Orthodox": "Death, not guilt, passes to all; humanity inherits corruption and mortality and then sins personally.",
            "Wesleyan / Arminian": "A corrupt nature is inherited, but prevenient grace restores sufficient freedom to respond to the gospel.",
            "Roman Catholic": "Original sin is the privation of original holiness, transmitted by propagation, removed as to guilt in baptism though concupiscence remains.",
        },
    },
    {
        "ref": "Romans 8:28-30",
        "topic": "The golden chain",
        "question": "Is predestination individual and unconditional?",
        "positions": {
            "Reformed": "The chain is unbroken — all who are foreknown are ultimately glorified — implying an effectual, unconditional individual election.",
            "Arminian / Wesleyan": "'Foreknew' denotes God's prior knowledge of who would believe; predestination concerns the destiny appointed for believers as a class.",
            "Corporate election": "The passage concerns the church as a people in Christ; individuals participate by union with Christ rather than by prior individual selection.",
            "Roman Catholic": "Predestination is affirmed while genuine cooperation with grace is maintained; Thomists and Molinists differ sharply on how.",
        },
    },
    {
        "ref": "Romans 9:6-24",
        "topic": "Election, vessels, and divine freedom",
        "question": "Does Paul teach unconditional individual election to salvation?",
        "positions": {
            "Reformed": "God's choice of Jacob over Esau 'before they had done anything' establishes unconditional election, and the potter imagery affirms God's absolute right.",
            "Arminian / Wesleyan": "The chapter concerns God's freedom in choosing instruments for historical purposes, not individuals' eternal destinies; Jacob and Esau stand for nations.",
            "Corporate / covenantal": "Paul's problem is why national Israel largely rejected the Messiah; the answer redefines who counts as Israel, not who is individually saved.",
            "Eastern Orthodox": "Divine foreknowledge does not determine; salvation is synergistic, and hardening is God's permission of a resistance already chosen.",
        },
    },
    {
        "ref": "Romans 13:1-7",
        "topic": "Submission to governing authorities",
        "question": "Is obedience to government unconditional?",
        "positions": {
            "Strong submission": "Authority is divinely instituted; resistance is resistance to God, and Paul wrote this under Nero.",
            "Qualified obedience": "Authorities are described as servants who punish evil and reward good; a regime inverting that forfeits the basis of the claim. Acts 5:29 limits obedience.",
            "Anabaptist": "Government is ordained for the world outside the church, and Christians submit without participating in coercive power.",
            "Liberationist": "Read alongside Revelation 13, where the state becomes a beast, the passage cannot be an unconditional endorsement of any regime.",
        },
    },
    {
        "ref": "1 Corinthians 11:2-16",
        "topic": "Head coverings and headship",
        "question": "Is the head covering a cultural practice or a standing requirement?",
        "positions": {
            "Cultural application": "Paul applies an enduring principle of order through a first-century Corinthian custom; the custom does not transfer.",
            "Perpetual ordinance": "Paul grounds the practice in creation and angels, not local custom, so it remains binding — the position of some Reformed, Anabaptist and Orthodox communities.",
            "Egalitarian": "*Kephalē* likely means 'source' rather than 'authority over', and verses 11-12 explicitly qualify the argument toward mutuality.",
        },
    },
    {
        "ref": "1 Corinthians 12:4-31",
        "topic": "Spiritual gifts",
        "question": "Do the miraculous gifts continue today?",
        "positions": {
            "Cessationist": "Sign gifts authenticated the apostolic message and ceased with the completion of the canon and the apostolic era.",
            "Continuationist": "Scripture nowhere announces the withdrawal of the gifts; they remain available to the church until Christ returns.",
            "Pentecostal / Charismatic": "The gifts are normative Christian experience, with tongues often understood as evidence of Spirit baptism.",
            "Open but cautious": "The gifts are not withdrawn in principle, but claims require careful testing against Scripture (1 Thessalonians 5:19-21).",
        },
    },
    {
        "ref": "1 Corinthians 15:20-28",
        "topic": "Resurrection and final subjection",
        "question": "What is the nature and order of the resurrection?",
        "positions": {
            "Historic / amillennial": "The resurrection of the dead is a single general event at Christ's return.",
            "Premillennial": "'Each in his own order' implies distinct stages separated by the millennial reign.",
            "Universalist reading": "'That God may be all in all' and 'in Christ all shall be made alive' have been read since Origen and Gregory of Nyssa as pointing to final universal restoration — a minority view.",
        },
    },
    {
        "ref": "Galatians 3:26-29",
        "topic": "Neither Jew nor Greek, slave nor free, male nor female",
        "question": "How far does this equality extend?",
        "positions": {
            "Egalitarian": "The verse abolishes status hierarchy in the new covenant community, including in ministry roles.",
            "Complementarian": "The verse concerns equal standing before God in salvation, which is compatible with distinct roles in church and household.",
            "Historical reading": "Paul's immediate argument is that Gentiles need not become Jews to be Abraham's heirs; the social implications are real but derivative.",
        },
    },
    {
        "ref": "Ephesians 2:8-10",
        "topic": "Grace, faith, and works",
        "question": "What is 'not of yourselves', and how do works relate to salvation?",
        "positions": {
            "Protestant (sola fide)": "Salvation is received by faith alone; works are its necessary fruit but contribute nothing to justification.",
            "Roman Catholic": "Initial justification is entirely unmerited grace, but justification involves genuine interior renewal, and grace-enabled works cooperate in growth in righteousness.",
            "Eastern Orthodox": "Salvation is participation in the divine life (*theosis*), a synergy of grace and free response rather than a forensic transaction.",
            "New Perspective on Paul": "'Works' primarily denotes covenant boundary markers — circumcision, food laws, sabbath — that excluded Gentiles, not moral effort in general.",
        },
    },
    {
        "ref": "1 Timothy 2:11-15",
        "topic": "Women teaching and exercising authority",
        "question": "Is this restriction universal or situational?",
        "positions": {
            "Complementarian": "Paul grounds the instruction in the creation order rather than local circumstance, making it a standing norm for church office.",
            "Egalitarian": "The verb *authentein* is rare and carries connotations of domineering; the instruction addresses a specific problem in Ephesus, likely involving false teaching.",
            "Historical-contextual": "Ephesus was the center of the Artemis cult, which shaped claims about women's priority; verse 15's reference to childbearing suggests a concrete local situation.",
            "Catholic and Orthodox": "Ordination is reserved to men on grounds of apostolic tradition and sacramental representation, distinct from the exegesis of this passage alone.",
        },
    },
    {
        "ref": "Hebrews 6:4-8",
        "topic": "Falling away",
        "question": "Can a genuine believer irrecoverably apostatize?",
        "positions": {
            "Reformed": "The described persons experienced the community's blessings without saving faith; genuine believers persevere because God preserves them.",
            "Arminian / Wesleyan": "The warning is real and addressed to real believers; salvation can be forfeited through deliberate, settled apostasy.",
            "Hypothetical reading": "The author frames an impossibility to shock complacent readers, not to describe an actual category.",
            "Catholic and Orthodox": "Mortal sin can sever communion with God, though repentance and restoration remain possible through the sacraments.",
        },
    },
    {
        "ref": "James 2:14-26",
        "topic": "Faith without works",
        "question": "Does James contradict Paul on justification?",
        "positions": {
            "Complementary-terms reading": "James and Paul use 'justify' differently — Paul of initial acceptance before God, James of the demonstration and vindication of genuine faith.",
            "Roman Catholic": "James shows that justification is not by faith alone; faith formed by love is what justifies, and works genuinely participate.",
            "Reformed": "Works are the necessary evidence of saving faith, never its ground; James attacks a dead orthodoxy, not Pauline doctrine.",
            "Historical-critical": "James may be responding to a distortion of Pauline teaching circulating in his communities rather than to Paul himself.",
        },
    },
    {
        "ref": "1 Peter 3:18-22",
        "topic": "Christ preaching to the spirits in prison",
        "question": "To whom did Christ preach, and when?",
        "positions": {
            "Harrowing of hell (Catholic, Orthodox, Lutheran)": "Between death and resurrection Christ descended to the realm of the dead and proclaimed his victory.",
            "Preaching through Noah": "The preincarnate Christ preached through Noah to that generation, who are now 'in prison' — Augustine's reading, common among the Reformed.",
            "Proclamation to fallen angels": "The 'spirits' are the disobedient angelic beings of Genesis 6 and 1 Enoch, and the proclamation is one of triumph rather than evangelism.",
        },
    },
    {
        "ref": "Colossians 2:16-17",
        "topic": "Sabbath and holy days",
        "question": "Does the fourth commandment still bind Christians?",
        "positions": {
            "Sabbatarian (Seventh-day Adventist, some Reformed)": "The moral law including the sabbath endures; the passage concerns ceremonial sabbaths, not the weekly commandment.",
            "Lord's Day / Christian sabbath": "The principle transfers to Sunday in commemoration of the resurrection.",
            "Fulfillment view": "The sabbath was a shadow whose substance is Christ; Romans 14:5 makes observance a matter of individual conscience.",
        },
    },
    {
        "ref": "2 Timothy 3:16-17",
        "topic": "Scripture, tradition, and sufficiency",
        "question": "Is Scripture the sole authority for doctrine?",
        "positions": {
            "Protestant (sola scriptura)": "Scripture is the sole infallible rule of faith; tradition and councils are useful but subordinate and correctable.",
            "Roman Catholic": "Scripture and apostolic Tradition together form one deposit of revelation, interpreted authoritatively by the Magisterium.",
            "Eastern Orthodox": "Scripture is the supreme expression of the church's Tradition and is rightly read within the church's liturgical and conciliar life.",
            "Contextual note": "The 'Scripture' Paul refers to is principally the Old Testament, since the New Testament canon was not yet closed.",
        },
    },
    {
        "ref": "Revelation 20:1-10",
        "topic": "The millennium",
        "question": "What is the thousand-year reign?",
        "positions": {
            "Amillennial": "The thousand years symbolize the present church age between Christ's advents; the binding of Satan restrains deception of the nations.",
            "Postmillennial": "The gospel will progressively christianize the world, producing an era of righteousness before Christ returns.",
            "Historic premillennial": "Christ returns before a literal earthly reign, with the church passing through tribulation.",
            "Dispensational premillennial": "A literal thousand-year reign follows the return, with Israel and the church kept distinct and the church removed beforehand.",
        },
    },
]
