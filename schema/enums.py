"""Canonical enumerations for MedAI-EPI phenotype ontology v0.1.

All string enums serialize as their .value. Terminology follows ILAE 2017
seizure/epilepsy classification and ILAE 2010 drug-resistance definition.
"""

from enum import Enum


class DocumentType(str, Enum):
    MRI_REPORT = "mri_report"
    EEG_REPORT = "eeg_report"
    PROGRESS_NOTE = "progress_note"
    INITIAL_CONSULT = "initial_consult"
    PRESURGICAL_EVALUATION = "presurgical_evaluation"
    EMU_ADMISSION = "emu_admission"
    EMU_DISCHARGE = "emu_discharge"
    SURGERY_CONFERENCE = "surgery_conference"
    PROCEDURE_SEEG = "procedure_seeg"
    PROCEDURE_RESECTION = "procedure_resection"
    PROCEDURE_NEUROSTIM = "procedure_neurostim"
    OTHER = "other"


class Certainty(str, Enum):
    """Confidence level of the extracted assertion in the source text."""
    DEFINITE = "definite"
    PROBABLE = "probable"
    POSSIBLE = "possible"
    NEGATED = "negated"
    UNKNOWN = "unknown"           # note explicitly states unknown
    NOT_DOCUMENTED = "not_documented"  # note does not address it


class TemporalStatus(str, Enum):
    CURRENT = "current"
    HISTORICAL = "historical"
    PLANNED = "planned"
    HYPOTHETICAL = "hypothetical"
    UNSPECIFIED = "unspecified"


class EpilepsyType(str, Enum):
    """ILAE 2017 top-level epilepsy classification."""
    FOCAL = "focal"
    GENERALIZED = "generalized"
    COMBINED_FOCAL_GENERALIZED = "combined_focal_generalized"
    UNKNOWN = "unknown"


# One wording for both readers (the model prompt v2 and the EpExtra rule).
UNKNOWN_EPILEPSY_TYPE_DEFINITION = (
    "the note says the patient has epilepsy but does not name its type "
    "(focal, generalized, or combined focal and generalized)")


class SeizureType(str, Enum):
    """ILAE 2017 basic seizure types."""
    FOCAL_AWARE = "focal_aware"
    FOCAL_IMPAIRED_AWARENESS = "focal_impaired_awareness"
    FOCAL_UNKNOWN_AWARENESS = "focal_unknown_awareness"
    FOCAL_TO_BILATERAL_TONIC_CLONIC = "focal_to_bilateral_tonic_clonic"
    GENERALIZED_TONIC_CLONIC = "generalized_tonic_clonic"
    GENERALIZED_TONIC = "generalized_tonic"
    GENERALIZED_CLONIC = "generalized_clonic"
    GENERALIZED_MYOCLONIC = "generalized_myoclonic"
    GENERALIZED_ABSENCE_TYPICAL = "generalized_absence_typical"
    GENERALIZED_ABSENCE_ATYPICAL = "generalized_absence_atypical"
    GENERALIZED_ATONIC = "generalized_atonic"
    GENERALIZED_EPILEPTIC_SPASMS = "generalized_epileptic_spasms"
    UNKNOWN_ONSET_TONIC_CLONIC = "unknown_onset_tonic_clonic"
    UNKNOWN_ONSET_MOTOR_OTHER = "unknown_onset_motor_other"
    UNKNOWN_ONSET_NONMOTOR = "unknown_onset_nonmotor"
    UNCLASSIFIED = "unclassified"


class Awareness(str, Enum):
    AWARE = "aware"
    IMPAIRED = "impaired"
    UNKNOWN = "unknown"


class Laterality(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    BILATERAL = "bilateral"
    MIDLINE = "midline"
    DIFFUSE = "diffuse"
    UNKNOWN = "unknown"


class LobarLocalization(str, Enum):
    FRONTAL = "frontal"
    TEMPORAL = "temporal"
    PARIETAL = "parietal"
    OCCIPITAL = "occipital"
    INSULAR = "insular"
    CINGULATE = "cingulate"
    MULTIFOCAL = "multifocal"
    UNKNOWN = "unknown"


class LocalizationSource(str, Enum):
    """Where a localization claim comes from (§5: distinguish hypothesis vs confirmed)."""
    CLINICIAN_HYPOTHESIS = "clinician_hypothesis"
    EEG_CONFIRMED = "eeg_confirmed"
    MRI_CONFIRMED = "mri_confirmed"
    SEEG_CONFIRMED = "seeg_confirmed"
    SURGICAL_CONFIRMED = "surgical_confirmed"


class EegStudyType(str, Enum):
    ROUTINE = "routine"
    PROLONGED = "prolonged"
    AMBULATORY = "ambulatory"
    VIDEO_EEG = "video_eeg"
    EMU = "emu"
    INTRAOPERATIVE = "intraoperative"
    SEEG = "seeg"
    ECOG = "ecog"


class EegBackground(str, Enum):
    NORMAL = "normal"
    DIFFUSE_SLOWING = "diffuse_slowing"
    FOCAL_SLOWING = "focal_slowing"
    ASYMMETRIC = "asymmetric"
    SUPPRESSED = "suppressed"
    BURST_SUPPRESSION = "burst_suppression"
    OTHER = "other"


class IedType(str, Enum):
    SPIKE = "spike"
    SHARP_WAVE = "sharp_wave"
    SPIKE_AND_WAVE = "spike_and_wave"
    POLYSPIKE = "polyspike"
    POLYSPIKE_AND_WAVE = "polyspike_and_wave"
    SHARP_AND_SLOW = "sharp_and_slow"
    GENERALIZED_SPIKE_WAVE_3HZ = "generalized_spike_wave_3hz"
    OTHER = "other"


class FrequencyBand(str, Enum):
    """EEG frequency band (SACAR / ACNS). Filled from a Hz figure or a band word."""
    DELTA = "delta"
    THETA = "theta"
    ALPHA = "alpha"
    BETA = "beta"
    GAMMA = "gamma"


class IedRecurrence(str, Enum):
    """How often the discharge occurs in the record (SACAR recurrence; ACNS quantity words)."""
    RARE = "rare"
    OCCASIONAL = "occasional"
    INTERMITTENT = "intermittent"
    FREQUENT = "frequent"
    ABUNDANT = "abundant"
    CONTINUOUS = "continuous"


class IedDispersal(str, Enum):
    """How widely the discharge is seen (SACAR dispersal). Not inferred from lobe alone."""
    FOCAL = "focal"
    REGIONAL = "regional"
    MULTIFOCAL = "multifocal"
    HEMISPHERIC = "hemispheric"
    GENERALIZED = "generalized"


class MriFinding(str, Enum):
    """Epilepsy-relevant MRI findings. Extended in v0.2 with MOGHE + FCD Palmini subtypes."""
    NORMAL = "normal"
    HIPPOCAMPAL_SCLEROSIS = "hippocampal_sclerosis"
    FOCAL_CORTICAL_DYSPLASIA = "focal_cortical_dysplasia"           # generic, unspecified subtype
    FCD_PALMINI_I = "fcd_palmini_i"
    FCD_PALMINI_IIA = "fcd_palmini_iia"
    FCD_PALMINI_IIB = "fcd_palmini_iib"
    MOGHE = "moghe"                                                  # Mild MCD with oligodendroglial hyperplasia
    TUMOR = "tumor"
    VASCULAR_MALFORMATION = "vascular_malformation"
    ENCEPHALOMALACIA = "encephalomalacia"
    GLIOSIS = "gliosis"
    STROKE_SEQUELAE = "stroke_sequelae"
    POLYMICROGYRIA = "polymicrogyria"
    HETEROTOPIA = "heterotopia"
    LISSENCEPHALY = "lissencephaly"
    TUBEROUS_SCLEROSIS = "tuberous_sclerosis"
    OTHER_LESION = "other_lesion"
    MRI_NEGATIVE = "mri_negative"


class DrugResistanceStatus(str, Enum):
    """ILAE 2010 definition: failure of two tolerated, appropriately chosen ASM schedules."""
    DRUG_RESPONSIVE = "drug_responsive"
    UNDEFINED = "undefined"
    DRUG_RESISTANT = "drug_resistant"


class MedicationStatus(str, Enum):
    CURRENT = "current"
    PRIOR = "prior"
    FAILED = "failed"
    DISCONTINUED_ADVERSE_EFFECT = "discontinued_adverse_effect"
    PLANNED = "planned"


class SurgeryType(str, Enum):
    RESECTION = "resection"
    LASER_ABLATION = "laser_ablation"
    DISCONNECTION = "disconnection"
    HEMISPHERECTOMY = "hemispherectomy"
    CALLOSOTOMY = "callosotomy"
    NEUROSTIMULATION_VNS = "neurostimulation_vns"
    NEUROSTIMULATION_RNS = "neurostimulation_rns"
    NEUROSTIMULATION_DBS = "neurostimulation_dbs"
    OTHER = "other"
    UNKNOWN = "unknown"                     # v0.2: for cases where the note references a prior surgery of unspecified type


class ConcordanceStatus(str, Enum):
    """Cross-modality localization agreement (§5 integrated phenotype)."""
    CONCORDANT = "concordant"
    PARTIALLY_CONCORDANT = "partially_concordant"
    DISCORDANT = "discordant"
    NOT_ASSESSED = "not_assessed"


# ---------------------------------------------------------------------------
# v0.2 additions (provisional — items marked * still need epileptologist review)
# ---------------------------------------------------------------------------


class EtiologyCategory(str, Enum):
    """ILAE 2017 etiology top-level categories (§2.1 of stress-test report). *"""
    STRUCTURAL = "structural"
    GENETIC = "genetic"
    INFECTIOUS = "infectious"
    IMMUNE = "immune"
    METABOLIC = "metabolic"
    UNKNOWN = "unknown"


class FocalMotorOnset(str, Enum):
    """ILAE 2017 focal motor-onset subtypes (§2.2 of stress-test report). *"""
    AUTOMATISMS = "automatisms"
    ATONIC = "atonic"
    CLONIC = "clonic"
    EPILEPTIC_SPASMS = "epileptic_spasms"
    HYPERKINETIC = "hyperkinetic"
    MYOCLONIC = "myoclonic"
    TONIC = "tonic"


class FocalNonmotorOnset(str, Enum):
    """ILAE 2017 focal non-motor-onset subtypes. *"""
    AUTONOMIC = "autonomic"
    BEHAVIOR_ARREST = "behavior_arrest"
    COGNITIVE = "cognitive"
    EMOTIONAL = "emotional"
    SENSORY = "sensory"


class EngelClass(str, Enum):
    """Engel post-surgical outcome classification."""
    IA = "IA"
    IB = "IB"
    IC = "IC"
    ID = "ID"
    IIA = "IIA"
    IIB = "IIB"
    IIC = "IIC"
    IID = "IID"
    IIIA = "IIIA"
    IIIB = "IIIB"
    IVA = "IVA"
    IVB = "IVB"
    IVC = "IVC"


class IlaeOutcome(str, Enum):
    """ILAE post-surgical outcome classes 1–6."""
    CLASS_1 = "1"
    CLASS_2 = "2"
    CLASS_3 = "3"
    CLASS_4 = "4"
    CLASS_5 = "5"
    CLASS_6 = "6"


class NonDrugTherapyType(str, Enum):
    KETOGENIC_DIET = "ketogenic_diet"
    MODIFIED_ATKINS = "modified_atkins"
    LOW_GLYCEMIC_INDEX = "low_glycemic_index"
    IVIG = "ivig"
    PLASMAPHERESIS = "plasmapheresis"
    STEROIDS = "steroids"
    RITUXIMAB = "rituximab"
    ACTH = "acth"
    OTHER = "other"


# ---------------------------------------------------------------------------
# v0.2.1 additions — etiology specifics with well-known autoantibodies
# ---------------------------------------------------------------------------


class CausativeAntibody(str, Enum):
    """Curated autoantibody list for immune etiology. Not exhaustive — use OTHER
    with `etiology_details_text` for rare antibodies. Cell-surface and intracellular
    antigens are both included because both can drive autoimmune epilepsy."""
    # Cell-surface antigens
    ANTI_LGI1 = "anti_lgi1"
    ANTI_CASPR2 = "anti_caspr2"
    ANTI_NMDAR = "anti_nmdar"
    ANTI_GABABR = "anti_gababr"
    ANTI_AMPAR = "anti_ampar"
    ANTI_DPPX = "anti_dppx"
    ANTI_GLYR = "anti_glyr"           # glycine receptor
    ANTI_IGLON5 = "anti_iglon5"
    ANTI_MGLUR5 = "anti_mglur5"
    # Intracellular antigens (often paraneoplastic)
    ANTI_HU = "anti_hu"                # ANNA-1
    ANTI_MA2 = "anti_ma2"
    ANTI_YO = "anti_yo"                # PCA-1
    ANTI_RI = "anti_ri"                # ANNA-2
    ANTI_AMPHIPHYSIN = "anti_amphiphysin"
    ANTI_GAD65 = "anti_gad65"
    ANTI_SOX1 = "anti_sox1"
    ANTI_CV2 = "anti_cv2"              # CRMP5
    ANTI_ZIC4 = "anti_zic4"
    # Catch-all
    OTHER = "other"
    NONE_DETECTED = "none_detected"
