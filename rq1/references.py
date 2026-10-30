"""Source-based facts and proof obligations for the bounded RQ1 corpus."""
from __future__ import annotations

import re


def reference(row, code):
    block, lines = row['block'], code.splitlines()
    facts = []
    def add(key, role, pattern, meaning, *, essential=True):
        found = [i + 1 for i, line in enumerate(lines) if re.search(pattern, line)]
        if not found:
            raise ValueError(f"{row['case_id']}: missing reference fact {key}: {pattern}")
        facts.append({'id': key, 'role': role, 'lines': found,
                      'meaning': meaning, 'essential': essential})
        return key

    source_argument = block.startswith(('CWE806', 'src-'))
    fn = next((f for f in ('strncat', 'strcat', 'strcpy', 'memcpy', 'SNPRINTF')
               if re.search(r'\b' + f + r'\(', code)), None)
    if block == 'CWE129':
        kind, capacity, extent = 'heap', 40, None
        mechanism = 'A ten-int heap object has valid indices 0 through 9. The input can be 11; the nonnegative-only guard admits it and buffer[data] writes outside the object.'
        repair = 'The repaired guard additionally requires data < 10.'
        operation = 'array index write'
        add('capacity', 'capacity', r'malloc\(10', 'Ten int elements: 40 bytes on LP64.')
        add('input_acquisition', 'context', r'fgets\(', 'Input is obtained from stdin; a decimal value such as 11 is possible.')
        add('extent', 'extent', r'atoi\(', 'The converted input supplies the index; it is not a constant derived from the witness label.')
        add('guard', 'guard', r'if \(data >= 0\)', 'This guard has no upper-bound restriction.')
        add('access', 'sink', r'buffer\[data\] = 1', 'The converted scalar is used as the index.')
    elif block.startswith('CWE131'):
        kind = 'heap' if row['cwe'] == 'CWE122' else 'stack'
        capacity, extent = 10, 40
        mechanism = 'The selected destination has 10 bytes. The operation requests ten int elements, a 40-byte access range on LP64.'
        repair = 'The repaired allocation reserves 10*sizeof(int), or 40 bytes.'
        operation = 'memcpy call' if fn else 'array write loop'
        add('capacity', 'capacity', r'(?:ALLOCA|malloc)\(10\)', 'The receiving allocation reserves ten bytes, not ten int elements.')
        add('extent', 'extent', r'10\*sizeof\(int\)|for \(i = 0; i < 10', 'Ten int elements require 40 bytes; a first-invalid-store account is also acceptable.')
        add('access', 'sink', r'memcpy\(|data\[i\] = source\[i\]', 'The operation writes through the selected destination pointer.')
        add('read_object', 'context', r'int source\[10\]', 'The read operand has ten int elements; its contents do not determine the copy count.', essential=False)
    elif block.startswith('CWE193'):
        kind, capacity, extent = 'stack', 10, 11
        mechanism = 'The source contains ten characters and a terminating NUL. The copy includes eleven bytes, while the selected destination has ten bytes.'
        repair = 'The repaired caller selects the eleven-byte object.'
        operation = 'strcpy call' if fn else 'array write loop'
        add('capacity', 'capacity', r'ALLOCA\(\(10\)', 'The selected receiving object has ten bytes.')
        add('string_definition', 'context', r'#define SRC_STRING', 'The macro supplies ten non-NUL characters; it cannot be inferred when omitted.')
        add('source_initialization', 'extent', r'char source\[10\+1\]', 'The source array is initialized with SRC_STRING.')
        add('extent', 'extent', r'strcpy\(|sourceLen =|for \(i =', 'strcpy includes the NUL; the loop variant explicitly includes sourceLen + 1.')
        add('access', 'sink', r'strcpy\(|data\[i\] = source\[i\]', 'The copy writes through the caller-selected pointer.')
    else:
        kind = 'stack' if source_argument or row['cwe'] == 'CWE121' else 'heap'
        capacity = 50
        extent = 99 if source_argument and (fn in {'SNPRINTF', 'memcpy'} or fn is None) else 100
        mechanism = f'The receiving object has 50 bytes; the documented count and source facts imply a requested {extent}-byte access range, exceeding its capacity.'
        repair = 'The repaired caller uses a shorter source.' if source_argument else 'The repaired caller selects or allocates a 100-byte destination.'
        operation = fn.lower() + ' call' if fn else 'array write loop'
        add('capacity', 'capacity', r'char dest\[50\]' if source_argument else r'(?:ALLOCA|malloc)\(50\*sizeof', 'The receiving object has fifty bytes.')
        access = re.escape(fn) + r'\(' if fn else r'dest\[i\] = data\[i\]|data\[i\] = source\[i\]'
        add('access', 'sink', access, 'The intended write operation, not a later consequence or unrelated access.')
        if block == 'CWE805-copy':
            # memcpy uses its explicit count, independently of source string contents.
            add('extent', 'extent', r'memcpy\(data, source, 100\*sizeof\(char\)\)', 'The count argument requests 100 bytes; source initialization does not set this count.')
            add('read_object', 'context', r'char source\[100\]', 'The read operand has a hundred bytes; this is source-object context, not the write count.', essential=False)
        else:
            add('source_initialization', 'extent', r'memset\(data,' if source_argument else r'memset\(source', 'The documented non-NUL initialization establishes the source content relevant to length.')
            add('source_termination', 'context', r'data\[100-1\]' if source_argument else r'source\[100-1\]', 'The explicit termination establishes the documented source length.')
            if source_argument:
                add('extent', 'extent', r'strlen\(data\)|dataLen =|for \(i =|strcpy\(|strcat\(', 'The access extent depends on the caller-supplied source length and operation semantics.')
                add('source_allocation', 'context', r'data = .*malloc|dataBuffer = .*ALLOCA', 'This allocation supplies the read operand, not the local overflowing destination.', essential=False)
            else:
                add('extent', 'extent', access, 'The count bound and/or string operation determines the access range together with the source facts.')
            if fn in {'strcat', 'strncat'} and not source_argument:
                add('destination_initialization', 'context', r'data\[0\] =', 'The destination initially denotes the empty string.')
        if fn == 'SNPRINTF':
            add('macro_binding', 'context', r'#define SNPRINTF snprintf', 'On the selected Linux branch SNPRINTF denotes standard snprintf; do not invent an omitted binding.')

    add('caller_argument', 'context', r'case_sink\(data\);', 'The selected entry supplies this actual argument.')
    add('callee_parameter', 'context', r'^(?:static )?void case_sink\(', 'The argument binds this formal parameter; equal spelling alone is not proof of identity.')
    if re.search(r'data = (?:buffer_\d+|dataBuffer);', code):
        add('alias_selection', 'context', r'data = (?:buffer_\d+|dataBuffer);', 'The assignment identifies which allocated object is actually passed.')
    ids = {f['id'] for f in facts}
    binding = ['caller_argument', 'callee_parameter'] + (['alias_selection'] if 'alias_selection' in ids else [])
    relation = ('The caller supplies the index scalar; the receiving buffer is allocated locally.' if block == 'CWE129'
                else 'The caller supplies the source object whose length drives the local destination write.' if source_argument
                else 'The caller supplies the destination object whose capacity is compared with the access.')
    determining = [f['id'] for f in facts if f['role'] == 'extent' or f['id'] in {'string_definition', 'source_termination', 'input_acquisition', 'macro_binding'}]
    relations = [
        {'id': 'bounds_violation', 'from': 'capacity', 'to': 'access', 'kind': 'access_exceeds_object_bound',
         'premise_ids': ['capacity', 'access', 'extent'], 'explanation': mechanism},
        {'id': 'extent_support', 'from': 'extent', 'to': 'access', 'kind': 'value_or_count_determines_access_range',
         'premise_ids': determining, 'explanation': 'Establish the relevant count, source length or possible index using visible facts and permitted assumptions.'},
        {'id': 'argument_binding', 'from': 'caller_argument', 'to': 'callee_parameter', 'kind': 'caller_argument_binding',
         'premise_ids': binding, 'explanation': relation},
    ]
    if block == 'CWE129':
        relations.append({'id': 'guard_context', 'from': 'guard', 'to': 'access', 'kind': 'guard_admits_invalid_index',
                          'premise_ids': ['guard', 'extent', 'capacity'], 'explanation': 'The selected input can exceed the object bound while satisfying the visible guard.'})
    return {'review_claim': {'flaw_class': kind + ' buffer overflow', 'operation': operation},
            'mechanism': mechanism, 'repair': repair, 'elements': facts, 'relations': relations,
            'checked_quantities': {'capacity_bytes': capacity, 'requested_access_bytes': extent,
                                   'invalid_index_example': 11 if block == 'CWE129' else None},
            'reference_basis': 'AI-assisted source reasoning, Juliet documentation, LP64 ABI and finite executable witnesses; independent of Q outputs, not independent human annotation',
            'assumptions': ['LP64 Linux: char=1, int=4, pointer/long=8 bytes',
                'Selected case_entry path and successful allocation/reachability',
                'Standard C library semantics; ALLOCA is the documented stack-allocation helper',
                'No hidden capacities, lengths, aliases, macro values or caller facts may be supplied'],
            'observed_storage_kind': kind}
