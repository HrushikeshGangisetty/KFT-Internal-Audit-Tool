import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../../lib/auth.jsx'
import { Card, Icon, PageHeader, when } from '../../components/ui.jsx'
import { Paged, usePaged } from '../../components/data.jsx'
import CustomerForm from './CustomerForm.jsx'

export default function CustomerList() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [adding, setAdding] = useState(false)
  const page = usePaged('/api/customers/')
  const p = user?.permissions ?? {}
  const canAdd = p.can_view_fcs && p.is_head_or_manager // customers.services.save_record
  return (
    <>
      <PageHeader title="Customers"
                  subtitle="Customer sites and the flight controllers deployed there."
                  actions={canAdd && !adding
                    ? <button onClick={() => setAdding(true)}><Icon name="plus" />Add a customer</button> : null} />
      {adding ? <CustomerForm onCancel={() => setAdding(false)}
                              onSaved={(c) => navigate(`/customers/${c.id}`)} /> : null}
      <Card title="All customers" flush>
        <Paged page={page} what="customers" cols={3} empty="No customers recorded yet." emptyIcon="list">
          {(rows) => (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Customer</th><th>Region</th><th>Updated</th></tr></thead>
                <tbody>{rows.map((c) => (
                  <tr key={c.id}>
                    <td><Link to={`/customers/${c.id}`}>{c.name}</Link></td>
                    <td>{c.region || <span className="muted">—</span>}</td>
                    <td className="small muted">{when(c.updated_at)}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </Paged>
      </Card>
    </>
  )
}
