import React, { useState } from 'react'
import {
  Sparkles,
  FolderPlus,
  Palette,
  Layers,
  CheckCircle2,
  X,
  ChevronRight,
  ChevronLeft,
  ShieldCheck,
  AlertTriangle,
  FileText
} from 'lucide-react'
import { codeRefactorApi } from '../../api'
import './ProjectWizardModal.css'

interface Props {
  onClose: () => void
  onSuccess: (data: any) => void
}

export const ProjectWizardModal: React.FC<Props> = ({ onClose, onSuccess }) => {
  const [step, setStep] = useState<number>(1)
  const [projectName, setProjectName] = useState<string>('Serenity Wellness Spa')
  const [targetPath, setTargetPath] = useState<string>('D:/Projects/SerenitySpa')
  const [techStack, setTechStack] = useState<string>('FastAPI + React')
  const [uiStyle, setUiStyle] = useState<string>('Glassmorphism')
  const [description, setDescription] = useState<string>('Autonomous wellness spa booking platform with UI/UX Pro Max design intelligence.')
  const [blueprintContent, setBlueprintContent] = useState<string>('')
  const [blueprintFilename, setBlueprintFilename] = useState<string>('')
  const [submitting, setSubmitting] = useState<boolean>(false)
  const [errorMessage, setErrorMessage] = useState<string>('')

  const isCPath = targetPath.toLowerCase().startsWith('c:')

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setBlueprintFilename(file.name)
    const reader = new FileReader()
    reader.onload = (event) => {
      setBlueprintContent(String(event.target?.result || ''))
    }
    reader.readAsText(file)
  }

  const handleNext = () => {
    if (step === 1 && (!projectName.trim() || !targetPath.trim())) {
      setErrorMessage('Please provide a valid project name and D:\\ target folder path.')
      return
    }
    if (step === 1 && isCPath) {
      setErrorMessage('SECURITY BLOCK: Writing to C:\\ OS drive is prohibited. Please specify a path on D:\\ drive (e.g. D:\\Projects\\...).')
      return
    }
    setErrorMessage('')
    setStep((prev) => Math.min(prev + 1, 4))
  }

  const handleBack = () => {
    setErrorMessage('')
    setStep((prev) => Math.max(prev - 1, 1))
  }

  const handleCreateProject = async () => {
    if (isCPath) {
      setErrorMessage('SECURITY BLOCK: Writing to C:\\ OS drive is prohibited. Please specify a path on D:\\ drive.')
      return
    }
    setSubmitting(true)
    setErrorMessage('')
    try {
      const resp = await codeRefactorApi.createScratch({
        project_name: projectName.trim(),
        target_path: targetPath.trim(),
        tech_stack: techStack,
        ui_style: uiStyle,
        description: description.trim(),
        blueprint_content: blueprintContent,
        blueprint_filename: blueprintFilename
      })
      onSuccess(resp.data)
      onClose()
    } catch (err: any) {
      console.error(err)
      setErrorMessage('Creation failed: ' + (err.response?.data?.detail || err.message))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="wizard-modal-overlay">
      <div className="wizard-modal">
        {/* Header */}
        <div className="wizard-modal-header">
          <div className="wizard-header-title">
            <Sparkles className="wizard-title-icon" size={22} />
            <div>
              <h3>From-Scratch Solution Setup Wizard</h3>
              <p>UI/UX Pro Max Design Intelligence & Autonomous Project Scaffolder</p>
            </div>
          </div>
          <button className="btn-icon" onClick={onClose}><X size={18} /></button>
        </div>

        {/* Step Indicator Bar */}
        <div className="wizard-steps-bar">
          <div className={`step-pill ${step >= 1 ? 'active' : ''}`}>1. Location & Name</div>
          <div className={`step-pill ${step >= 2 ? 'active' : ''}`}>2. Tech Stack</div>
          <div className={`step-pill ${step >= 3 ? 'active' : ''}`}>3. UI/UX Pro Max Theme</div>
          <div className={`step-pill ${step >= 4 ? 'active' : ''}`}>4. Confirm & Scaffold</div>
        </div>

        {errorMessage && (
          <div className="wizard-error-banner">
            <AlertTriangle size={16} /> {errorMessage}
          </div>
        )}

        {/* Wizard Body */}
        <div className="wizard-modal-body">
          {step === 1 && (
            <div className="wizard-step-content">
              <h4><FolderPlus size={18} /> Step 1: Project Name & Drive Location</h4>
              <div className="wizard-field">
                <label>Project Name</label>
                <input
                  type="text"
                  className="wizard-input"
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  placeholder="e.g. Serenity Spa"
                />
              </div>

              <div className="wizard-field">
                <label>Target Directory Path (Must be on D:\ Drive)</label>
                <input
                  type="text"
                  className={`wizard-input ${isCPath ? 'input-error' : ''}`}
                  value={targetPath}
                  onChange={(e) => setTargetPath(e.target.value)}
                  placeholder="e.g. D:/Projects/SerenitySpa"
                />
                {isCPath ? (
                  <span className="field-hint hint-danger">
                    <AlertTriangle size={12} /> C:\ drive writes are blocked to protect operating system files. Use D:\ drive.
                  </span>
                ) : (
                  <span className="field-hint hint-success">
                    <ShieldCheck size={12} /> D:\ drive write access granted.
                  </span>
                )}
              </div>

              <div className="wizard-field">
                <label>Solution Goal & Summary</label>
                <textarea
                  className="wizard-textarea"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Describe what this new app or tool will do..."
                  rows={3}
                />
              </div>

              <div className="wizard-field">
                <label>Optional Architecture Spec / Blueprint Upload (.md, .txt, .json)</label>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 4 }}>
                  <input
                    type="file"
                    accept=".md,.txt,.json,.pdf,.doc"
                    id="wizard-blueprint-upload"
                    style={{ display: 'none' }}
                    onChange={handleFileUpload}
                  />
                  <label htmlFor="wizard-blueprint-upload" className="btn btn-secondary" style={{ cursor: 'pointer', fontSize: '0.8rem' }}>
                    <FileText size={14} /> {blueprintFilename ? 'Change Blueprint File' : 'Attach Blueprint Spec (.md)'}
                  </label>
                  {blueprintFilename && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(56, 189, 248, 0.15)', padding: '4px 10px', borderRadius: 6, fontSize: '0.78rem', color: '#38bdf8' }}>
                      <FileText size={12} />
                      <span>{blueprintFilename} ({Math.round((blueprintContent.length / 1024) * 10) / 10} KB)</span>
                      <button className="btn-icon" onClick={() => { setBlueprintContent(''); setBlueprintFilename(''); }}>
                        <X size={12} />
                      </button>
                    </div>
                  )}
                </div>
                <span className="field-hint" style={{ fontSize: '0.72rem', color: '#94a3b8', marginTop: 4, display: 'block' }}>
                  Upload an architectural blueprint spec markdown file to guide AI solution scaffolding.
                </span>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="wizard-step-content">
              <h4><Layers size={18} /> Step 2: Tech Stack Selection</h4>
              <p className="step-subtext">Choose the underlying framework and architecture for scaffolding:</p>

              <div className="tech-stack-options">
                {[
                  { name: 'FastAPI + React', desc: 'Full-stack app with Python REST backend & Vite React frontend.' },
                  { name: 'Python CLI Tool', desc: 'Standalone command-line automation tool with argparse & logging.' },
                  { name: 'Next.js + Tailwind', desc: 'Modern React SSR app with Tailwind CSS styling.' },
                  { name: 'Express + React', desc: 'Node.js REST API with React frontend.' }
                ].map((option) => (
                  <div
                    key={option.name}
                    className={`stack-option-card ${techStack === option.name ? 'selected' : ''}`}
                    onClick={() => setTechStack(option.name)}
                  >
                    <div className="stack-option-title">{option.name}</div>
                    <div className="stack-option-desc">{option.desc}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="wizard-step-content">
              <h4><Palette size={18} /> Step 3: UI/UX Pro Max Design Style Selection</h4>
              <p className="step-subtext">Select curated design system tokens (79 UI styles, color palettes & Google Fonts):</p>

              <div className="ui-style-options">
                {[
                  { id: 'Glassmorphism', name: 'Glassmorphism Dark', desc: 'Soft frosted depth, glowing accents, premium feel.' },
                  { id: 'Soft UI', name: 'Soft UI Evolution', desc: 'Subtle shadows, warm organic shapes, calming wellness feel.' },
                  { id: 'Clean SaaS Dark', name: 'Clean SaaS Dark', desc: 'Plus Jakarta Sans typography, high contrast dashboard elements.' },
                  { id: 'Developer Dark', name: 'Developer IDE Dark', desc: 'JetBrains Mono monospace font, dark slate neon cyan accents.' }
                ].map((style) => (
                  <div
                    key={style.id}
                    className={`style-option-card ${uiStyle === style.id ? 'selected' : ''}`}
                    onClick={() => setUiStyle(style.id)}
                  >
                    <div className="style-option-title">{style.name}</div>
                    <div className="style-option-desc">{style.desc}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {step === 4 && (
            <div className="wizard-step-content">
              <h4><CheckCircle2 size={18} /> Step 4: Review Architecture & Confirm Scaffolding</h4>
              <div className="summary-box">
                <div className="summary-row"><span>Project Name:</span> <strong>{projectName}</strong></div>
                <div className="summary-row"><span>Target Path:</span> <strong className="text-success">{targetPath}</strong></div>
                <div className="summary-row"><span>Tech Stack:</span> <strong>{techStack}</strong></div>
                <div className="summary-row"><span>UI/UX Style:</span> <strong className="text-primary">{uiStyle}</strong></div>
              </div>

              <div className="scaffold-files-preview">
                <label>Boilerplate Files to Scaffold:</label>
                <ul>
                  <li><code>README.md</code> (Project Documentation & Quickstart)</li>
                  <li><code>requirements.txt</code> (FastAPI & Pydantic dependencies)</li>
                  <li><code>package.json</code> (React, Vite & Lucide SVG icons)</li>
                  <li><code>backend/main.py</code> (FastAPI REST API entry point)</li>
                  <li><code>src/App.tsx</code> (React component with UI/UX Pro Max CSS design tokens)</li>
                  <li><code>src/index.css</code> (Custom CSS variables: --primary-color, --bg-color)</li>
                </ul>
              </div>
            </div>
          )}
        </div>

        {/* Footer Controls */}
        <div className="wizard-modal-footer">
          {step > 1 ? (
            <button className="btn btn-secondary" onClick={handleBack} disabled={submitting}>
              <ChevronLeft size={16} /> Back
            </button>
          ) : <div />}

          {step < 4 ? (
            <button className="btn btn-primary" onClick={handleNext}>
              Next <ChevronRight size={16} />
            </button>
          ) : (
            <button className="btn btn-success" onClick={handleCreateProject} disabled={submitting}>
              <Sparkles size={16} /> {submitting ? 'Scaffolding Solution...' : 'Create Project From Scratch'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export default ProjectWizardModal
