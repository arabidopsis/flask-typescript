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
