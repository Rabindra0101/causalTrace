export class ApiResponseError extends Error {
  status: number
  component?: string
  constructor(message: string, status: number, component?: string) {
    super(message)
    this.status = status
    this.component = component
  }
}

export class BackendUnavailableError extends Error {}

export async function jsonResponse(response: Response) {
  const text = await response.text()
  let data
  try { data = JSON.parse(text) }
  catch { throw new BackendUnavailableError('Cannot check setup: backend unavailable or returned an invalid response.') }
  if (!response.ok) {
    const detail = data.detail
    throw new ApiResponseError(typeof detail === 'string' ? detail : detail?.message ?? 'Request failed',
      response.status, typeof detail === 'object' ? detail?.component : undefined)
  }
  return data
}

export function readinessFailure(error: unknown): { component: string; message: string } | null {
  if (error instanceof BackendUnavailableError || error instanceof TypeError) {
    return {component:'backend', message:'Cannot check — backend unavailable'}
  }
  if (error instanceof ApiResponseError && (error.component || error.status === 503)) {
    return {component:error.component ?? 'docker', message:error.message}
  }
  if (error instanceof ApiResponseError && error.message.startsWith('Git investigation failed')) {
    return {component:'git', message:'A Git operation failed for this repository. Check the backend terminal for details.'}
  }
  return null
}
