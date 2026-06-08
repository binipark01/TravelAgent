import { AssumptionsPanel } from './AssumptionsPanel'
import { MissingFieldsPanel } from './MissingFieldsPanel'

export function TripInterpretationPanel({
  missingFields,
  assumptions,
}: {
  missingFields: string[]
  assumptions: string[]
}) {
  return (
    <section className="interpretation-grid">
      <MissingFieldsPanel fields={missingFields} />
      <AssumptionsPanel assumptions={assumptions} />
    </section>
  )
}
