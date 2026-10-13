"""Generate two labelled synthetic PDFs and a controlled naming/kind matrix."""
import json
from pathlib import Path
from reportlab.pdfgen.canvas import Canvas

root = Path(__file__).resolve().parent
lines = ['SYNTHETIC - string kind and date controls', 'Example Works', 'International Shipping',
         'May 1, 2026', '2026-02-30', '03/04/2026', 'YYYY-MM-DD', 'Alpha 10.00', 'Beta 10.00']
for name, extra in [('plain', []), ('mixed', ['31/12/2025', '12/31/2025'])]:
    canvas = Canvas(str(root / f'{name}.pdf'), pagesize=(612,792), invariant=True)
    canvas.setTitle('Synthetic string-kind controls')
    for index, text in enumerate(lines + extra):
        canvas.drawString(50, 750 - 30 * index, text)
    canvas.save()

cases = []
def case(id, name, before, after, *, shape='leaf', kind='inferred', value='Example Works',
         quote=None, pdf='plain', tolerance=0, default=None, conflicts=None):
    cases.append(dict(id=id, name=name, shape=shape, kind=kind, value=value,
                      quote=value if quote is None else quote, pdf=pdf, tolerance=tolerance,
                      defaultDateOrder=default, expectedBefore=before, expectedAfter=after,
                      expectedConflict=conflicts))

V, R, U = 'verified', 'needs_review', 'unsupported'
case('ordinary-control','name',[V],[V])
for name in ['candidate_name','candidateName','updated_by','validate_status','consolidated_notes']:
    case(name,name,[R],[V])
case('ancestor-model','name',[R],[V],shape='nested')
case('mapping-key','candidate_name',[R],[V],shape='mapping')
case('mapping-ancestor','name',[R],[V],shape='mapped-model')
case('date-sequence-control','dates',[R],[R],shape='sequence',value='2026-02-30')
case('written-date-control','issue_date',[V],[V],value='2026-05-01',quote='May 1, 2026')
case('camel-date-control','dueDate',[R],[R],value='2026-02-30')
case('birthdate-control','birthdate',[R],[R],value='2026-02-30')
case('text-tolerance','candidate_name',[R],[V],value='Internationxl Shipping',quote='International Shipping',tolerance=1)
case('text-conflict-note','candidate_name',[R],[R],value='Example Workx',quote='Example Works',pdf='mixed',conflicts=[True,False])
case('explicit-written-date','effective',[R],[V],kind='date',value='2026-05-01',quote='May 1, 2026')
case('explicit-invalid-date','effective',[V],[R],kind='date',value='2026-02-30')
case('explicit-text-label','date_label',[R],[V],kind='text',value='YYYY-MM-DD')
case('explicit-date-no-tolerance','effective',[V],[R],kind='date',value='Internationxl Shipping',quote='International Shipping',tolerance=1)
case('explicit-date-conflict','effective',[R],[R],kind='date',value='2026-03-04',quote='03/04/2026',pdf='mixed',default='dmy',conflicts=[False,True])
case('explicit-mapped-date','slot-A',[V],[R],shape='mapped-sequence',kind='date',value='2026-02-30')
case('explicit-text-row-anchor','date_label',[R,R],[V,V],shape='row',kind='text',value='Alpha')
case('explicit-unsupported','effective',[U],[U],kind='date',value='2026-05-01',quote='')
(root/'cases.json').write_text(json.dumps(dict(label='All inputs are synthetic controls.',cases=cases),indent=2)+'\n')
