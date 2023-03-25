
export type ValidationError = {
    loc: string[]
    msg: string
    type: string
}[]

export type Result<T> = { success: true, result: T } | { success: false, error: ValidationError }

export type FuncExtra = {
    arg: Arg
    extra: number
}
export type ArgXX = {
    query: string
}
export type FuncArg5 = {
    extra: ArgXX[]
}
export type FuncArg6 = {
    extra: ArgXX[]
}
export type FuncFull = {
    arg: Arg
    extra?: number /* =1 */
}
export type Arg = {
    query: string
    selected: number[]
    doit?: boolean /* =false */
    date: string
    val: number
    arg5: Arg5
    checked?: string[] /* =['aaa'] */
}
export type Ret1 = {
    val: string[]
    res: string
}
export type FuncQqq = {
    a: number
    b?: number /* =5 */
}
export type Json = {
    a: number
    b: number
}
export type Arg5 = {
    query: string
}
export interface Base {
    full: (arg: Arg, extra?: number /* =1 */)=> Promise<Arg>
    qqq: (a: number, b?: number /* =5 */)=> Promise<Arg5>
    filestorage: (val: number[], myfiles: File[])=> Promise<Ret1>
    extra: (arg: Arg, extra: number)=> Promise<Response>
    arg5: (extra: ArgXX[])=> Promise<Arg5>
    arg6: (extra: ArgXX[])=> Promise<Arg5>
    json: ()=> Promise<Json>
}
