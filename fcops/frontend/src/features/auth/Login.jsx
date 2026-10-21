import { useState } from 'react'
import { useAuth } from '../../lib/auth.jsx'
import { Banner, Card, Field, useTitle } from '../../components/ui.jsx'
import { Brand } from '../../app/Shell.jsx'

export default function Login() {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useTitle('Sign in')

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await login(username, password)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
      <div className="login-brand"><Brand /></div>
      <Card as="form" title="Sign in" subtitle="Use your engineering account credentials." onSubmit={submit}>
        <Banner>{error}</Banner>
        <Field label="Username">
          <input value={username} onChange={(e) => setUsername(e.target.value)}
                 autoFocus autoComplete="username" />
        </Field>
        <Field label="Password">
          <input type="password" value={password} autoComplete="current-password"
                 onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <button disabled={busy || !username || !password} style={{ width: '100%' }}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </Card>
      </div>
    </div>
  )
}
