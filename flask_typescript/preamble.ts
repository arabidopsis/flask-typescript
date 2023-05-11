export type ValidationError = {
    loc: string[]
    msg: string
    type: string
}[]

export type Result<T> =
    | { type: 'success', result: T }
    | { type: 'failure', error: ValidationError }
    | { type: 'error', error: any }
