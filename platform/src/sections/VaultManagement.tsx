import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Key, Download } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { useSandbox } from '@/lib/sandbox-store'
import { api } from '@/lib/api'

export function VaultManagement() {
  const { vaultKeys, refresh } = useSandbox()
  const [key, setKey] = useState('')
  const [value, setValue] = useState('')

  const handleStore = async () => {
    if (!key.trim() || !value.trim()) return
    try {
      await api.setVaultSecret(key.trim(), value.trim())
      toast.success(`Stored ${key}`)
      setKey('')
      setValue('')
      await refresh()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed')
    }
  }

  const handleExport = async () => {
    try {
      const pack = await api.exportEvidence()
      const blob = new Blob([JSON.stringify(pack, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `erasys-evidence-${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      toast.success('Evidence pack exported')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Export failed')
    }
  }

  return (
    <section className="max-w-4xl mx-auto px-6 py-8">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-amber-600 flex items-center justify-center">
          <Key className="w-5 h-5 text-white" />
        </div>
        <div>
          <h2 className="text-2xl font-bold">Credential Vault</h2>
          <p className="text-sm text-gray-400">AES-256-GCM encrypted secrets for tool integrations</p>
        </div>
        <Button onClick={handleExport} variant="outline" className="ml-auto border-[#334155] gap-2">
          <Download className="w-4 h-4" /> Export Evidence Pack
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="bg-[#0f172a] border-[#1e293b]">
          <CardContent className="p-6 space-y-4">
            <h3 className="font-semibold">Store Secret</h3>
            <Input placeholder="Key (e.g. GITHUB_TOKEN)" value={key} onChange={(e) => setKey(e.target.value)} className="bg-[#1e293b] border-[#334155]" />
            <Input placeholder="Value" type="password" value={value} onChange={(e) => setValue(e.target.value)} className="bg-[#1e293b] border-[#334155]" />
            <Button onClick={handleStore} className="bg-amber-600 hover:bg-amber-700">Store Encrypted</Button>
          </CardContent>
        </Card>

        <Card className="bg-[#0f172a] border-[#1e293b]">
          <CardContent className="p-6">
            <h3 className="font-semibold mb-4">Stored Keys</h3>
            <div className="space-y-2">
              {vaultKeys.map((k) => (
                <div key={k.key} className="flex justify-between p-3 bg-[#1e293b]/50 rounded">
                  <span className="text-sm font-mono">{k.key}</span>
                  <Badge className="bg-[#1e293b] text-gray-400">{k.masked}</Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </section>
  )
}
