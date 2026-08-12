import { GitBranch, Globe, Heart } from 'lucide-react'

export function Footer() {
  return (
    <footer className="border-t border-[#1e293b] mt-12">
      <div className="max-w-7xl mx-auto px-6 py-8">
        <div className="flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-6 h-6 bg-[#4361ee] rotate-45 flex items-center justify-center">
              <span className="text-white font-bold text-[8px] -rotate-45">E</span>
            </div>
            <span className="text-sm text-gray-400">Erasys Intelligence Platform</span>
          </div>
          <div className="flex items-center gap-4">
            <a
              href="https://erasys.co.uk"
              target="_blank"
              rel="noopener noreferrer"
              className="text-gray-400 hover:text-white transition-colors flex items-center gap-1.5 text-sm"
            >
              <Globe className="w-4 h-4" /> erasys.co.uk
            </a>
            <a
              href="https://github.com/ibrahimmukherjee-boop/erasys-sandbox"
              target="_blank"
              rel="noopener noreferrer"
              className="text-gray-400 hover:text-white transition-colors flex items-center gap-1.5 text-sm"
            >
              <GitBranch className="w-4 h-4" /> GitHub
            </a>
          </div>
          <p className="text-xs text-gray-600 flex items-center gap-1">
            Built with <Heart className="w-3 h-3 text-red-400" /> by Erasys
          </p>
        </div>
      </div>
    </footer>
  )
}
