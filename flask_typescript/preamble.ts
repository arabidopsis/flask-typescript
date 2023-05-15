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
