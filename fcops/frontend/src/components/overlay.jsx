import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { Icon } from './ui.jsx'

/* ---------------------------------------------------------------------------
   Dialogs: one native <dialog> for the app, replacing window.prompt/confirm.
   `ask(opts)` resolves to null when cancelled, otherwise { text, choice }.
     opts: title, message, input: { label, placeholder, required = true },
           confirmLabel, tone ('danger' | 'ok'), choices: [{ value, label, tone }]
   ------------------------------------------------------------------------- */
const DialogContext = createContext(null)

export function DialogProvider({ children }) {
  const ref = useRef(null)
  const [req, setReq] = useState(null)
  const [text, setText] = useState('')

  useEffect(() => { if (req && !ref.current?.open) ref.current?.showModal() }, [req])

  const ask = useCallback((opts) => new Promise((resolve) => {
    setText('')
    setReq({ ...opts, resolve })
  }), [])

  const close = (result) => {
    ref.current?.close()
    req?.resolve(result)
    setReq(null)
  }
  const needsText = req?.input && req.input.required !== false
  const choices = req?.choices ?? [{ value: 'ok', label: req?.confirmLabel ?? 'OK', tone: req?.tone }]

  return (
    <DialogContext.Provider value={ask}>
      {children}
      <dialog ref={ref} className="dialog" aria-labelledby="dialog-title"
              onCancel={(e) => { e.preventDefault(); close(null) }}>
        {req ? (
          <form onSubmit={(e) => {
            e.preventDefault()
            close({ text: text.trim(), choice: e.nativeEvent.submitter?.value ?? choices[0].value })
          }}>
            <h2 id="dialog-title">{req.title}</h2>
            {req.message ? <p className="dialog-message">{req.message}</p> : null}
            {req.input ? (
              <div className="field">
                <label htmlFor="dialog-input">{req.input.label}</label>
                <textarea id="dialog-input" autoFocus value={text} required={needsText}
                          placeholder={req.input.placeholder} onChange={(e) => setText(e.target.value)} />
              </div>
            ) : null}
            <div className="row end">
              <button type="button" className="secondary" onClick={() => close(null)}>Cancel</button>
              {choices.map((c) => (
                <button key={c.value} value={c.value} className={c.tone || ''}
                        disabled={needsText && !text.trim()}>{c.label}</button>
              ))}
            </div>
          </form>
        ) : null}
      </dialog>
    </DialogContext.Provider>
  )
}

export const useDialog = () => useContext(DialogContext)

/* ---------------------------------------------------------------------------
   Toasts: short confirmations that do not push the page around. Errors stay
   as inline banners next to the action that failed.
   ------------------------------------------------------------------------- */
const ToastContext = createContext(() => {})

export function ToastProvider({ children }) {
  const [items, setItems] = useState([])
  const push = useCallback((text, kind = 'ok') => {
    const id = `${Date.now()}-${Math.random()}`
    setItems((xs) => [...xs, { id, text, kind }])
    setTimeout(() => setItems((xs) => xs.filter((t) => t.id !== id)), 4000)
  }, [])
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`}>
            <Icon name={t.kind === 'ok' ? 'check' : 'info'} />{t.text}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export const useToast = () => useContext(ToastContext)
