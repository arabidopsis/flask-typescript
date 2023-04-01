//>Y
export type Y = {
    y: number
}
//>Z
export type Z = {
    z: number
}
//>X
export type X = {
    val?: number /* =5 */
    val2: string
    my: [Y,Z]
    my2?: Y | Z /* =Y(y=1) */
}
//>Arg
export type Arg = {
    query: string
    selected: number[]
    doit?: boolean /* =false */
    date: string
    val: number
    arg5: Z
    checked?: string[] /* =['aaa'] */
}
//>WithAnnotated
export type WithAnnotated = {
    query: number
}
//>GenericPY
export type GenericPY<T= number | string> = {
    value: T
    values: T[]
}
//>GenericList
export type GenericList<T= number | string> = {
    value: T[]
}
//>SelfReference
export type SelfReference = {
    a?: number /* =123 */
    b?: SelfReference | null /* =null */
}
//>GenericTuple
export type GenericTuple<T= number | string> = {
    value: [T,number]
}
