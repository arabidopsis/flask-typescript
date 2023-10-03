export type ValidationError = {
    loc: string[]
    msg: string
    type: string
}[]

export type FlaskResult<
    Success extends Record<string, unknown> | undefined = Record<string, any>,
    Invalid extends ValidationError = ValidationError
> =
    | { type: 'success'; result: Success }
    | { type: 'failure'; errors: Invalid }
    | { type: 'error'; error: any }

export type ResultOf<T extends (...args: any) => any> = Awaited<ReturnType<T>>

export type Success<T extends (...args: any) => any> = Extract<ResultOf<T>, { type: 'success' }>['result']
