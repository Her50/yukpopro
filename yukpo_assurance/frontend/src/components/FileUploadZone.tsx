import { useCallback } from 'react'
import { useDropzone, FileWithPath } from 'react-dropzone'
import { clsx } from 'clsx'
import { DocumentArrowUpIcon, XMarkIcon } from '@heroicons/react/24/outline'

interface FileUploadZoneProps {
  onFilesAccepted: (files: FileWithPath[]) => void
  accept?: Record<string, string[]>
  maxFiles?: number
  currentFiles?: FileWithPath[]
  onRemoveFile?: (index: number) => void
  className?: string
  label?: string
}

export function FileUploadZone({
  onFilesAccepted,
  accept,
  maxFiles = 5,
  currentFiles = [],
  onRemoveFile,
  className,
  label = 'Glissez vos fichiers ici ou cliquez pour parcourir',
}: FileUploadZoneProps) {
  const onDrop = useCallback(
    (acceptedFiles: FileWithPath[]) => {
      onFilesAccepted(acceptedFiles)
    },
    [onFilesAccepted]
  )

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept,
    maxFiles,
  })

  return (
    <div className={className}>
      <div
        {...getRootProps()}
        className={clsx(
          'flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-8 text-center cursor-pointer transition-colors',
          isDragActive
            ? 'border-primary-500 bg-primary-50'
            : 'border-gray-300 bg-gray-50 hover:border-primary-400 hover:bg-primary-50/30'
        )}
      >
        <input {...getInputProps()} />
        <DocumentArrowUpIcon className="h-10 w-10 text-gray-400 mb-3" />
        <p className="text-sm font-medium text-gray-600">{label}</p>
        <p className="text-xs text-gray-400 mt-1">PDF, DOCX, JPG, PNG jusqu'à 10 Mo</p>
      </div>

      {currentFiles.length > 0 && (
        <ul className="mt-3 space-y-2">
          {currentFiles.map((file, idx) => (
            <li
              key={idx}
              className="flex items-center justify-between rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm"
            >
              <span className="truncate text-gray-700 max-w-xs">{file.name}</span>
              <button
                type="button"
                onClick={() => onRemoveFile?.(idx)}
                className="ml-2 text-gray-400 hover:text-red-500 transition-colors"
              >
                <XMarkIcon className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
