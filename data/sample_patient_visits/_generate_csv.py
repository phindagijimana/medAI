"""One-off generator for patient_visits.csv — run: python3 _generate_csv.py"""
import csv
from pathlib import Path

ROWS = [
    {
        "patient_id": "SYN-EP-001",
        "visit_id": "VIS-2024-0142",
        "visit_date": "2024-01-15",
        "specialty": "Epilepsy",
        "chief_complaint": "Staring spells and brief confusion",
        "clinical_note": """OUTPATIENT NEUROLOGY — FOLLOW-UP

HPI: 14 y/o referred for episodes of behavioral arrest lasting 1–2 minutes with lip smacking and post-ictal confusion. No witnessed convulsions. Sleep deprivation may trigger events.

EEG REPORT (Routine 30-min, awake/sleep):
Technique: International 10–20 system; awake, drowsy, and stage II sleep recorded.
Findings: Frequent left anterior temporal sharp waves, maximal at F7/T3, increasing during drowsiness. Independent right temporal slowing during hyperventilation only.
Impression: Focal epileptiform discharges, left temporal region, consistent with focal epilepsy. Clinical correlation recommended.

MRI BRAIN (3T, epilepsy protocol, same week):
Technique: Sagittal T1, axial/coronal T2-FLAIR, axial DWI, coronal T2 hippocampal oblique.
Findings: Subtle increased FLAIR signal and mild volume loss left hippocampus without mesial temporal sclerosis criteria fully met. No mass or acute infarct.
Impression: Left mesial temporal signal change; correlate with EEG and semiology.

ASSESSMENT: Focal impaired awareness seizures, likely left temporal onset.
PLAN: Start levetiracetam 500 mg BID; driving restrictions per state law; neurology follow-up 8 weeks.""",
    },
    {
        "patient_id": "SYN-EP-002",
        "visit_id": "VIS-2024-0201",
        "visit_date": "2024-02-03",
        "specialty": "Epilepsy",
        "chief_complaint": "Generalized jerks on awakening",
        "clinical_note": """EEG LAB — INTERPRETATION ADDENDUM (Outpatient)

Indication: Juvenile myoclonic epilepsy suspected; family history of epilepsy.

EEG REPORT:
Awake: Normal posterior dominant rhythm. Generalized 4–6 Hz polyspike-wave bursts with photic stimulation at medium rates; no prolonged discharges.
Sleep: Fragmented stage II; similar generalized polyspike-wave during arousals.
Impression: Generalized epileptiform pattern consistent with genetic generalized epilepsy; correlate with myoclonus history.

MRI BRAIN:
Not performed this visit (not clinically indicated per ILAE workup pathway for classic JME presentation).

ASSESSMENT: Probable JME.
PLAN: Counsel sleep hygiene; avoid sodium channel blockers if treatment initiated; follow-up with epilepsy attending.""",
    },
    {
        "patient_id": "SYN-ST-001",
        "visit_id": "VIS-2024-0310",
        "visit_date": "2024-03-10",
        "specialty": "Vascular neurology",
        "chief_complaint": "Right-sided weakness and slurred speech",
        "clinical_note": """EMERGENCY DEPARTMENT — NEUROLOGY CONSULT

HPI: 72 y/o with sudden onset right hemiparesis and dysarthria. Last known well 2.5 hours prior. Afib, not on anticoagulation.

MRI BRAIN (acute stroke protocol):
DWI: Restricted diffusion left frontoparietal cortex and corona radiata in MCA territory.
FLAIR: No established chronic infarct in opposite hemisphere.
MRA head/neck: High-grade M1 left occlusion.
Impression: Acute left MCA territory ischemic stroke; large vessel occlusion.

EEG:
Not obtained (acute stroke with obtundation; priority was reperfusion). If seizures develop, obtain bedside EEG.

ASSESSMENT: Acute ischemic stroke, L MCA occlusion; NIHSS 14.
PLAN: IV alteplase per protocol; neurointerventional team for thrombectomy consideration; ICU monitoring.""",
    },
    {
        "patient_id": "SYN-ST-002",
        "visit_id": "VIS-2024-0418",
        "visit_date": "2024-04-18",
        "specialty": "Vascular neurology",
        "chief_complaint": "TIA symptoms resolved",
        "clinical_note": """OUTPATIENT STROKE CLINIC

HPI: Brief episode of right arm weakness and word-finding difficulty lasting 20 minutes, fully resolved. Hypertension, hyperlipidemia.

MRI BRAIN:
DWI: Small punctate acute/subacute lacunar-type lesion left corona radiata (4 mm) without territorial pattern.
FLAIR: Chronic microvascular changes; no hemorrhage.
Impression: Recent small vessel ischemic event; correlate with TIA presentation.

CAROTID US: No hemodynamically significant stenosis.

EEG:
Not indicated for typical TIA without seizure suspicion.

ASSESSMENT: TIA versus small stroke; ABCD2 used for risk stratification.
PLAN: Dual antiplatelet per high-risk TIA protocol if applicable; high-intensity statin; BP control; neurology and PCP follow-up.""",
    },
    {
        "patient_id": "SYN-PD-001",
        "visit_id": "VIS-2024-0522",
        "visit_date": "2024-05-22",
        "specialty": "Movement disorders",
        "chief_complaint": "Tremor and slowness",
        "clinical_note": """MOVEMENT DISORDERS — INITIAL VISIT

HPI: 67 y/o with 3-year progressive rest tremor R>L, bradykinesia, mild rigidity. UPDRS motor subset suggests moderate burden. Reports wearing-off of levodopa before next dose.

MRI BRAIN:
No acute process. Mild nonspecific periventricular T2 hyperintensities for age. No midbrain atrophy pattern suggesting PSP; no cerebellar atrophy suggesting MSA.
Impression: Structurally unremarkable for alternative parkinsonism on this study.

EEG:
Not routinely indicated for Parkinson disease diagnosis (clinical diagnosis per MDS criteria).

ASSESSMENT: Idiopathic Parkinson disease, Hoehn & Yahr stage II–III range clinically.
PLAN: Optimize carbidopa/levodopa dosing; discuss COMT inhibitor for wearing-off; PT referral.""",
    },
    {
        "patient_id": "SYN-MG-001",
        "visit_id": "VIS-2024-0605",
        "visit_date": "2024-06-05",
        "specialty": "Neuromuscular",
        "chief_complaint": "Double vision and ptosis worse end of day",
        "clinical_note": """NEUROMUSCULAR CLINIC

HPI: Fluctuating diplopia and eyelid droop worsening with fatigue; improves with rest. No limb weakness reported.

MRI BRAIN/ORBITS:
Brain: Normal. Orbits: No compressive optic neuropathy; extraocular muscles within normal caliber on orbital sequences.
Impression: No structural cause for diplopia on MRI.

EEG:
Not indicated.

ASSESSMENT: Suspected myasthenia gravis; edrophonium test not performed in clinic today.
PLAN: Acetylcholine receptor antibodies; refer for EMG/RNS; discuss pyridostigmine if confirmed.""",
    },
    {
        "patient_id": "SYN-MS-001",
        "visit_id": "VIS-2024-0712",
        "visit_date": "2024-07-12",
        "specialty": "Neuroimmunology",
        "chief_complaint": "Optic neuritis history, follow-up",
        "clinical_note": """MS CLINIC — FOLLOW-UP

HPI: Prior episode of painful vision loss OD with recovery; now mild residual color desaturation.

MRI BRAIN AND SPINE (McDonald criteria surveillance):
Brain: Periventricular and juxtacortical ovoid T2/FLAIR lesions perpendicular to ventricles; no enhancing lesions today.
Spine: Cervical T2 hyperintense lesion C3–C4 without cord expansion.
Impression: Findings consistent with demyelinating disease; dissemination in space demonstrated.

EEG:
Not part of standard MS monitoring; obtained only if seizure develops.

ASSESSMENT: Relapsing MS on DMT; stable MRI compared to prior year.
PLAN: Continue current therapy; annual MRI brain/cervical spine; vision clinic PRN.""",
    },
    {
        "patient_id": "SYN-HA-001",
        "visit_id": "VIS-2024-0801",
        "visit_date": "2024-08-01",
        "specialty": "Headache",
        "chief_complaint": "Severe unilateral orbital headaches with tearing",
        "clinical_note": """HEADACHE CLINIC

HPI: Episodes of 45–90 min unilateral periorbital pain with ipsilateral lacrimation and nasal congestion, 1–2 times daily for 3 weeks in a cluster pattern.

MRI BRAIN:
No posterior fossa mass, no pituitary lesion, no vascular malformation. Paranasal sinuses clear.
Impression: Unremarkable MRI; appropriate to exclude secondary headache in new thunderclap or atypical features (not present here).

EEG:
Not indicated for trigeminal autonomic cephalalgias when MRI normal and history typical.

ASSESSMENT: Episodic cluster headache (ICHD-3 framework — clinical diagnosis).
PLAN: Acute oxygen and triptan therapy education; verapamil preventive discussion with EKG monitoring plan; neurology follow-up.""",
    },
    {
        "patient_id": "SYN-DM-001",
        "visit_id": "VIS-2024-0909",
        "visit_date": "2024-09-09",
        "specialty": "Cognitive / dementia",
        "chief_complaint": "Memory decline",
        "clinical_note": """COGNITIVE NEUROLOGY

HPI: 78 y/o with insidious progressive memory loss and word-finding difficulty; MoCA 19 today.

MRI BRAIN:
Hippocampal volume loss bilaterally with disproportionate atrophy of medial temporal lobes. Global cortical atrophy mild-moderate. No acute infarct. No frontal pattern suggesting FTD on imaging alone.
Impression: Neurodegenerative pattern most compatible with Alzheimer-type pathology on imaging; clinical correlation.

EEG:
Mild diffuse slowing of background rhythm for age; no epileptiform discharges. Useful to screen for subclinical seizures if episodic confusion worsens.

ASSESSMENT: Major neurocognitive disorder, likely etiology Alzheimer disease (pending biomarkers).
PLAN: Cholinesterase inhibitor discussion; safety and driving assessment; follow-up.""",
    },
    {
        "patient_id": "SYN-EP-003",
        "visit_id": "VIS-2024-1025",
        "visit_date": "2024-10-25",
        "specialty": "Epilepsy monitoring unit",
        "chief_complaint": "Presurgical evaluation",
        "clinical_note": """EMU SUMMARY — DAY 3

HPI: Drug-resistant focal epilepsy; admitted for phase I monitoring.

EEG (continuous inpatient video-EEG):
Recorded multiple focal impaired awareness seizures with stereotyped oral automatisms; ictal pattern: rhythmic theta/delta left temporal region evolving to rhythmic spiking. Post-ictal slowing left temporal.
Impression: Seizures of left temporal neocortical/mesial onset; concordant with prior studies.

MRI BRAIN (3T):
Left hippocampal sclerosis imaging criteria borderline; subtle FLAIR increase. Rest of study unchanged from prior.
Impression: Mesial temporal structural abnormality; surgical candidacy discussion separately.

ASSESSMENT: Localization-related epilepsy, left temporal; drug-resistant.
PLAN: Case conference for epilepsy surgery vs RNS candidacy; continue current ASM temporarily.""",
    },
]

FIELDNAMES = [
    "patient_id",
    "visit_id",
    "visit_date",
    "specialty",
    "chief_complaint",
    "clinical_note",
]


def main():
    out = Path(__file__).parent / "patient_visits.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        for row in ROWS:
            w.writerow(row)
    print(f"Wrote {len(ROWS)} rows to {out}")


if __name__ == "__main__":
    main()
