"""
Content Safety & Moderation Layer
─────────────────────────────────
Filters user input AND AI output for medical-sensitive children's storytelling.
- Blocks inappropriate / dangerous medical advice
- Ensures age-appropriate language
- Screens for harmful, violent, or scary content
- Validates medical condition descriptions
"""

import re
import logging
from typing import Tuple, List

logger = logging.getLogger('brave_story.content_safety')

# ── Blocked terms: content that should NEVER appear ────────────────────────
BLOCKED_TERMS = [
    # Violence / horror — note: 'blood' is intentionally excluded here because
    # legitimate medical conditions reference it (blood disorder, blood cancer,
    # sickle cell). Output moderation still filters gory contexts via
    # moderate_image_prompt.
    r'\b(kill|murder|suicide|self[- ]?harm|gore|weapon|gun|knife|stab)\b',
    # Sexual content
    r'\b(sex|nude|naked|pornograph|erotic|molest|rape)\b',
    # Substance abuse
    r'\b(drug\s*abuse|overdose|cocaine|heroin|meth|marijuana|alcohol\s*abuse)\b',
    # Dangerous medical advice
    r'\b(stop\s*taking\s*(your\s*)?medi(cation|cine)|don\'?t\s*go\s*to\s*(the\s*)?doctor)\b',
    r'\b(cure\s*yourself|no\s*need\s*for\s*treatment|reject\s*(your\s*)?treatment)\b',
    # Discrimination
    r'\b(racist|sexist|homophob|transphob|slur|hate\s*speech)\b',
    # Fear-inducing phrases — 'terminal'/'fatal'/'die' alone are too broad
    # (block legitimate condition descriptions); only block clearly negative phrasings.
    r'\b(will\s*die|no\s*hope|give\s*up|hopeless)\b',
]

BLOCKED_PATTERNS = [re.compile(pat, re.IGNORECASE) for pat in BLOCKED_TERMS]

# ── Warning terms: flag for review but allow through ───────────────────────
WARNING_TERMS = [
    r'\b(needle|injection|surgery|hospital|pain|scared|cry|hurt)\b',
    r'\b(chemotherapy|radiation|dialysis|transplant)\b',
]
WARNING_PATTERNS = [re.compile(pat, re.IGNORECASE) for pat in WARNING_TERMS]

# ── Age-inappropriate vocabulary by age group ──────────────────────────────
AGE_INAPPROPRIATE = {
    'young': {  # ages 3-7
        'patterns': [
            r'\b(devastating|catastrophic|agonizing|excruciating|terminal|metastasis)\b',
            r'\b(mortality|prognosis|palliative|intravenous|subcutaneous)\b',
        ],
        'max_sentence_length': 20,  # words per sentence
    },
    'middle': {  # ages 8-12
        'patterns': [
            r'\b(terminal|metastasis|mortality|palliative)\b',
        ],
        'max_sentence_length': 35,
    },
    'teen': {  # ages 13+
        'patterns': [],
        'max_sentence_length': 50,
    },
}

# ── Positive framing requirements ──────────────────────────────────────────
POSITIVE_INDICATORS = [
    r'\b(brave|courage|strong|hero|power|super|magic|friend|love|hope|smile|happy)\b',
    r'\b(adventure|discover|learn|grow|overcome|triumph|win|succeed)\b',
    r'\b(kind|gentle|warm|safe|protect|care|help|support)\b',
]
POSITIVE_PATTERNS = [re.compile(pat, re.IGNORECASE) for pat in POSITIVE_INDICATORS]

# ── Allowed medical conditions (validated categories) ──────────────────────
ALLOWED_CONDITION_CATEGORIES = [
    'asthma', 'diabetes', 'epilepsy', 'allergy', 'allergies',
    'broken bone', 'broken leg', 'broken arm', 'fracture',
    'cancer', 'leukemia', 'tumor',
    'heart condition', 'heart disease', 'heart surgery',
    'adhd', 'autism', 'down syndrome', 'cerebral palsy',
    'eczema', 'psoriasis', 'alopecia',
    'hearing loss', 'deaf', 'blind', 'vision loss',
    'wheelchair', 'prosthetic', 'amputation',
    'anxiety', 'depression', 'ocd',
    'sickle cell', 'hemophilia', 'cystic fibrosis',
    'ibd', 'crohn', 'colitis',
    'pneumonia', 'bronchitis', 'flu', 'covid',
    'surgery', 'operation', 'hospital stay',
    'cast', 'brace', 'crutches', 'walker',
    'speech therapy', 'physical therapy', 'occupational therapy',
    'tonsils', 'appendix', 'sprain', 'concussion',
]


def get_age_group(age: int) -> str:
    if age <= 7:
        return 'young'
    elif age <= 12:
        return 'middle'
    return 'teen'


def validate_input(child_name: str, age: int, condition: str,
                   hero_characteristics: str) -> Tuple[bool, str]:
    """
    Validate user input before sending to AI.
    Returns (is_valid, error_message).
    """
    errors = []

    # Name validation
    if not child_name or len(child_name.strip()) < 1:
        errors.append('Child name is required.')
    if len(child_name) > 50:
        errors.append('Child name is too long (max 50 characters).')
    if re.search(r'[<>&"\';\\/]', child_name):
        errors.append('Child name contains invalid characters.')

    # Age validation
    if age < 2 or age > 18:
        errors.append('Age must be between 2 and 18.')

    # Condition validation
    if not condition or len(condition.strip()) < 2:
        errors.append('Medical condition is required.')
    if len(condition) > 200:
        errors.append('Condition description is too long (max 200 characters).')

    # Check for blocked content in all free-text inputs, including the medical
    # 'condition' field. Legitimate medical vocabulary ("blood disorder",
    # "terminal", "leukemia") is protected by keeping those words OUT of
    # BLOCKED_TERMS — not by exempting the field — so violence/abuse tokens
    # ("kill", "weapon") are still rejected here.
    for field_name, field_val in [('name', child_name),
                                   ('condition', condition),
                                   ('characteristics', hero_characteristics)]:
        for pattern in BLOCKED_PATTERNS:
            if pattern.search(field_val):
                errors.append(f'Input contains inappropriate content in {field_name}.')
                logger.warning(f'Blocked content in {field_name}: {pattern.pattern}')
                break

    # Injection prevention — block prompt injection attempts.
    # Patterns require word boundaries / explicit phrasing to avoid blocking
    # ordinary user text like "loves {video games}" or names containing "act as".
    injection_patterns = [
        r'\bignore\s+(previous|above|all)\s+(instructions|prompts)\b',
        r'\byou\s+are\s+now\b',
        r'\bsystem\s+prompt\b',
        r'\bforget\s+(everything|all)\b',
        r'\bact\s+as\s+(a|an)\s+\w+',
        r'\bpretend\s+to\s+be\b',
    ]
    for field_val in [child_name, condition, hero_characteristics]:
        for pat in injection_patterns:
            if re.search(pat, field_val, re.IGNORECASE):
                errors.append('Input contains suspicious content. Please use simple descriptions.')
                logger.warning(f'Potential prompt injection detected: {pat}')
                break

    if errors:
        return False, '; '.join(errors)
    return True, ''


def moderate_output(text: str, age: int) -> Tuple[str, List[str]]:
    """
    Moderate AI-generated story text.
    Returns (cleaned_text, list_of_warnings).
    """
    warnings = []
    cleaned = text

    # Check for blocked content
    for pattern in BLOCKED_PATTERNS:
        matches = pattern.findall(cleaned)
        if matches:
            for match in matches:
                warnings.append(f'Removed blocked term: "{match}"')
                logger.warning(f'Blocked term found in output: {match}')
            cleaned = pattern.sub('***', cleaned)

    # Check age appropriateness
    age_group = get_age_group(age)
    age_config = AGE_INAPPROPRIATE[age_group]

    for pat_str in age_config['patterns']:
        pattern = re.compile(pat_str, re.IGNORECASE)
        matches = pattern.findall(cleaned)
        if matches:
            for match in matches:
                warnings.append(f'Age-inappropriate term replaced: "{match}"')
            cleaned = pattern.sub('[special word]', cleaned)

    # Check sentence length for young children
    if age_group == 'young':
        sentences = re.split(r'[.!?]+', cleaned)
        long_sentences = [s for s in sentences if len(s.split()) > age_config['max_sentence_length']]
        if long_sentences:
            warnings.append(f'{len(long_sentences)} sentences may be too long for age {age}')

    # Verify positive framing
    positive_count = sum(1 for p in POSITIVE_PATTERNS if p.search(cleaned))
    if positive_count < 2:
        warnings.append('Story may lack sufficient positive/empowering language')

    return cleaned, warnings


def moderate_image_prompt(prompt: str) -> Tuple[str, List[str]]:
    """
    Moderate image generation prompts.
    Returns (cleaned_prompt, warnings).
    """
    warnings = []
    cleaned = prompt

    # Block inappropriate image content
    image_blocked = [
        r'\b(scary|horror|blood|gore|weapon|violent|dark|creepy|monster|demon)\b',
        r'\b(realistic\s*medical|surgical\s*scene|open\s*wound|scar)\b',
        r'\b(needle|syringe|iv\s*drip|hospital\s*bed)\b',
    ]

    for pat_str in image_blocked:
        pattern = re.compile(pat_str, re.IGNORECASE)
        matches = pattern.findall(cleaned)
        if matches:
            for match in matches:
                warnings.append(f'Removed from image prompt: "{match}"')
            cleaned = pattern.sub('magical', cleaned)

    # Ensure child-safe framing
    safety_suffix = (
        ' Child-safe, bright colors, cheerful atmosphere, '
        'no scary elements, no medical equipment visible, '
        'cartoon style, warm and friendly.'
    )
    if 'child-safe' not in cleaned.lower():
        cleaned += safety_suffix

    return cleaned, warnings


def sanitize_html(text: str) -> str:
    """Strip HTML tags and dangerous URL/event handler syntax.

    Returns plain text with tags removed. We do NOT HTML-entity-escape here:
    sanitize_html is run repeatedly on stored values (e.g. on every edit), and
    escaping & on each pass would compound into &amp;amp;... Frontends and
    template engines are responsible for context-appropriate escaping on
    render.
    """
    if not isinstance(text, str):
        return text
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Remove script-like content
    text = re.sub(r'javascript:', '', text, flags=re.IGNORECASE)
    text = re.sub(r'on\w+\s*=', '', text, flags=re.IGNORECASE)
    return text
