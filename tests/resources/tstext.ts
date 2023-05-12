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
//>LinkedList
export type LinkedList = {
    a?: number /* =123 */
    b?: LinkedList | null /* =null */
}
//>GenericTuple
export type GenericTuple<T= number | string> = {
    value: [T,number]
}
//>Child
export type Child = {
    val: number
}
//>Parent
export type Parent = {
    child: Child
}
