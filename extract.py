import os
import shutil
"""
Script to extract last submissions into processed folder
"""

if not (os.path.exists('processed')):
    os.mkdir('processed')
counter = 0
for hw in filter(lambda name: name[0] == 'K', next(os.walk('Masinõpe'))[1]):
    student_codes = next(os.walk(f'Masinõpe\\{hw}'))[1]
    for code in student_codes:
        submissions = next(os.walk(f'Masinõpe\\{hw}\\{code}'))[1]
        if len(submissions) < 2:
            counter += 1
            continue
        if not (os.path.exists(f'processed\\{hw}\\{code}')):
            os.makedirs(f'processed\\{hw}\\{code}')

        a = [*sorted(filter(lambda file: not (file.endswith('.ceg')), submissions), reverse=True)]
        tasks = next(os.walk(f'Masinõpe\\{hw}\\{code}\\{a[0]}'))[2]
        for task in tasks:
            shutil.copyfile(f'Masinõpe\\{hw}\\{code}\\{a[0]}\\{task}', f'processed\\{hw}\\{code}\\{task}')

print(f"There was {counter} missing submission(s)")
